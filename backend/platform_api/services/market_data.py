from datetime import datetime, timedelta, timezone as dt_timezone
import json
from math import sin
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.utils import timezone

from ..models import MarketDataCache


BINANCE_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}
TIMEFRAME_TO_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


class MarketDataUnavailableError(ValueError):
    pass


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace("-", "").upper()


def get_candles(symbol: str, timeframe: str, limit: int = 500, force_refresh: bool = False) -> list[dict]:
    normalized_symbol = normalize_symbol(symbol)
    if timeframe not in BINANCE_INTERVALS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    cache_entry = MarketDataCache.objects.filter(
        symbol=normalized_symbol,
        timeframe=timeframe,
        limit=limit,
    ).first()

    ttl = timedelta(seconds=settings.MARKET_DATA_CACHE_TTL_SECONDS)
    if cache_entry and not force_refresh and timezone.now() - cache_entry.updated_at <= ttl:
        return cache_entry.payload

    query_string = urlencode({"symbol": normalized_symbol, "interval": timeframe, "limit": limit})
    failures: list[str] = []
    for base_url in _candidate_base_urls():
        try:
            with urlopen(f"{base_url}/api/v3/klines?{query_string}", timeout=15) as response:
                raw_payload = response.read().decode("utf-8")
            api_payload = json.loads(raw_payload)
            payload = _normalize_klines_payload(api_payload)
            MarketDataCache.objects.update_or_create(
                symbol=normalized_symbol,
                timeframe=timeframe,
                limit=limit,
                defaults={"payload": payload},
            )
            return payload
        except HTTPError as exc:
            failures.append(_format_http_error(base_url, exc))
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{base_url}: {exc}")

    if cache_entry and cache_entry.payload:
        return cache_entry.payload

    if settings.MARKET_DATA_FALLBACK_MODE == "synthetic":
        payload = _generate_synthetic_candles(normalized_symbol, timeframe, limit)
        MarketDataCache.objects.update_or_create(
            symbol=normalized_symbol,
            timeframe=timeframe,
            limit=limit,
            defaults={"payload": payload},
        )
        return payload

    detail = failures[0] if failures else "unknown upstream error"
    raise MarketDataUnavailableError(
        f"Unable to load market data for {normalized_symbol} on {timeframe}. Upstream detail: {detail}"
    )


def latest_price(symbol: str, timeframe: str = "1h") -> float:
    candles = get_candles(symbol, timeframe, limit=2)
    if not candles:
        raise ValueError(f"No candle data returned for {symbol}")
    return float(candles[-1]["close"])


def _candidate_base_urls() -> list[str]:
    configured = settings.BINANCE_API_BASE_URL.rstrip("/")
    candidates = [configured]
    for fallback in ("https://api.binance.com", "https://api.binance.us"):
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates


def _normalize_klines_payload(api_payload: list[list]) -> list[dict]:
    payload = []
    for item in api_payload:
        payload.append(
            {
                "time": datetime.fromtimestamp(item[0] / 1000, tz=dt_timezone.utc).isoformat(),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        )
    return payload


def _format_http_error(base_url: str, exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:  # pragma: no cover - defensive fallback
        body = str(exc)
    return f"{base_url}: HTTP {exc.code} {body}"


def _generate_synthetic_candles(symbol: str, timeframe: str, limit: int) -> list[dict]:
    step_minutes = TIMEFRAME_TO_MINUTES[timeframe]
    anchor = timezone.now().astimezone(dt_timezone.utc).replace(second=0, microsecond=0)
    base_price = 50 + (sum(ord(char) for char in symbol) % 400)
    candles: list[dict] = []

    for index in range(limit):
        point_time = anchor - timedelta(minutes=step_minutes * (limit - index - 1))
        trend = index * 0.28
        seasonal = sin(index / 6) * 4.5
        drift = ((index % 7) - 3) * 0.22
        close_price = max(1.0, base_price + trend + seasonal + drift)
        candle_bias = sin(index / 2.4) * 0.95 + (((index % 6) - 2.5) * 0.22)
        open_price = max(1.0, close_price + candle_bias)
        high_price = max(open_price, close_price) + 0.85 + ((index % 4) * 0.05)
        low_price = min(open_price, close_price) - 0.9 - ((index % 3) * 0.04)
        volume = 800 + (index * 11) + ((index % 9) * 23)

        candles.append(
            {
                "time": point_time.isoformat(),
                "open": round(open_price, 4),
                "high": round(high_price, 4),
                "low": round(max(0.1, low_price), 4),
                "close": round(close_price, 4),
                "volume": round(volume, 4),
            }
        )

    return candles
