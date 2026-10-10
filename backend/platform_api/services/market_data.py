from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import json
from math import cos, sin
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from platform_api.models import MarketDataCache
from .alpaca_client import get_alpaca_client

SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}
TIMEFRAME_TO_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# Standard realistic baseline prices for Forex major & minor pairs
FOREX_BASE_PRICES = {
    "EURUSD": 1.0850,
    "GBPUSD": 1.2950,
    "USDJPY": 152.40,
    "USDCHF": 0.8850,
    "AUDUSD": 0.6550,
    "USDCAD": 1.3850,
    "NZDUSD": 0.5920,
    "EURGBP": 0.8380,
    "EURJPY": 165.35,
    "GBPJPY": 197.35,
    "AUDJPY": 99.85,
    "CADJPY": 110.05,
    "EURAUD": 1.6560,
    "EURCAD": 1.5030,
    "GBPAUD": 1.9770,
    "GBPCAD": 1.7940,
    # Equities & Crypto
    "AAPL": 336.64,
    "TSLA": 242.50,
    "NVDA": 138.25,
    "MSFT": 428.50,
    "AMZN": 186.40,
    "GOOGL": 165.80,
    "META": 585.00,
    "SPY": 584.20,
    "QQQ": 492.50,
    "BTCUSD": 63450.0,
    "ETHUSD": 2650.0,
}

# Typical spread in pips per pair
FOREX_SPREADS_PIPS = {
    "EURUSD": 0.8,
    "GBPUSD": 1.2,
    "USDJPY": 0.9,
    "USDCHF": 1.5,
    "AUDUSD": 1.1,
    "USDCAD": 1.4,
    "NZDUSD": 1.8,
    "EURGBP": 1.2,
    "EURJPY": 1.5,
    "GBPJPY": 2.2,
}


class MarketDataUnavailableError(ValueError):
    pass


def normalize_symbol(symbol: str) -> str:
    """Normalize any symbol representation into clean uppercase format (e.g. EURUSD)."""
    return symbol.replace("/", "").replace("_", "").replace("-", "").upper()


def format_display_symbol(symbol: str) -> str:
    """Formats 'EURUSD' into 'EUR/USD', 'BTCUSD' into 'BTC/USD', etc."""
    norm = normalize_symbol(symbol)
    crypto_bases = {"BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB", "XAU", "XAG"}
    for base in crypto_bases:
        if norm.startswith(base) and norm.endswith("USD"):
            return f"{base}/USD"
        if norm == base:
            return f"{base}/USD"
    if len(norm) == 6:
        return f"{norm[:3]}/{norm[3:]}"
    return norm


def get_forex_quote(symbol: str) -> dict:
    """
    Returns latest bid, ask, mid price and spread for a forex or crypto pair.
    """
    norm = normalize_symbol(symbol)

    from .order_execution import OrderExecutionService
    if OrderExecutionService.get_active_broker() == "mt5":
        try:
            from .mt5_client import get_mt5_client
            client = get_mt5_client()
            if client.is_connected():
                import MetaTrader5 as mt5
                actual = client._resolve_symbol(symbol)
                if actual:
                    tick = mt5.symbol_info_tick(actual)
                    sym_info = mt5.symbol_info(actual)
                    if tick and sym_info:
                        is_crypto = any(k in norm for k in ("BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB")) or tick.bid > 500
                        if is_crypto:
                            spread_val = round(tick.ask - tick.bid, 2 if tick.bid > 1.0 else 4)
                            spread_pips = spread_val
                        else:
                            pip_size = 0.01 if "JPY" in norm else 0.0001
                            spread_pips = round(sym_info.spread * sym_info.point / pip_size, 1)

                        mid = round((tick.bid + tick.ask) / 2.0, sym_info.digits)
                        return {
                            "symbol": format_display_symbol(symbol),
                            "normalized_symbol": norm,
                            "bid": round(tick.bid, sym_info.digits),
                            "ask": round(tick.ask, sym_info.digits),
                            "mid": mid,
                            "spread_pips": spread_pips,
                            "source": "MetaTrader 5 (Exness)",
                            "timestamp": timezone.now().isoformat(),
                        }
        except Exception:
            pass

    mid = latest_price(norm, timeframe="1m")
    pip_size = 0.01 if "JPY" in norm else 0.0001
    spread_pips = FOREX_SPREADS_PIPS.get(norm, 1.2)
    half_spread = (spread_pips * pip_size) / 2.0

    bid = round(mid - half_spread, 5 if "JPY" not in norm else 3)
    ask = round(mid + half_spread, 5 if "JPY" not in norm else 3)

    return {
        "symbol": format_display_symbol(symbol),
        "normalized_symbol": norm,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pips": spread_pips,
        "timestamp": timezone.now().isoformat(),
    }


def _fetch_mt5_bars(symbol: str, timeframe: str, limit: int) -> list[dict]:
    """
    Fetch real historical candles directly from connected Exness MT5 terminal.
    """
    try:
        from .mt5_client import get_mt5_client
        client = get_mt5_client()
        if not client.is_connected():
            return []
        import MetaTrader5 as mt5
        actual = client._resolve_symbol(symbol)
        if not actual:
            return []
        tf_map = {
            "1m": mt5.TIMEFRAME_M1,
            "5m": mt5.TIMEFRAME_M5,
            "15m": mt5.TIMEFRAME_M15,
            "1h": mt5.TIMEFRAME_H1,
            "4h": mt5.TIMEFRAME_H4,
            "1d": mt5.TIMEFRAME_D1,
        }
        mt5_tf = tf_map.get(timeframe, mt5.TIMEFRAME_H1)
        rates = mt5.copy_rates_from_pos(actual, mt5_tf, 0, limit)
        if rates is None or len(rates) == 0:
            return []
        candles = []
        for r in rates:
            dt = datetime.fromtimestamp(r[0], tz=dt_timezone.utc).isoformat()
            candles.append({
                "time": dt,
                "timestamp": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": int(r[5]),
            })
        return candles
    except Exception:
        return []


def get_candles(symbol: str, timeframe: str = "1h", limit: int = 500, force_refresh: bool = False) -> list[dict]:
    """
    Fetch OHLCV candles for a given symbol and timeframe.
    Tries real MT5 first, then Alpaca, then realistic synthesis.
    """
    normalized_symbol = normalize_symbol(symbol)
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}. Must be one of {SUPPORTED_TIMEFRAMES}")

    cache_entry = MarketDataCache.objects.filter(
        symbol=normalized_symbol,
        timeframe=timeframe,
        limit=limit,
    ).first()

    ttl = timedelta(seconds=getattr(settings, "MARKET_DATA_CACHE_TTL_SECONDS", 60))
    if cache_entry and not force_refresh and timezone.now() - cache_entry.updated_at <= ttl:
        return cache_entry.payload

    # 1. Attempt to load real historical candles from MetaTrader 5 (Exness)
    try:
        mt5_bars = _fetch_mt5_bars(normalized_symbol, timeframe, limit)
        if mt5_bars and len(mt5_bars) > 0:
            MarketDataCache.objects.update_or_create(
                symbol=normalized_symbol,
                timeframe=timeframe,
                limit=limit,
                defaults={"payload": mt5_bars},
            )
            return mt5_bars
    except Exception:
        pass

    # 2. Attempt to load candles from Alpaca API if available
    try:
        alpaca_bars = _fetch_alpaca_bars(normalized_symbol, timeframe, limit)
        if alpaca_bars and len(alpaca_bars) > 0:
            MarketDataCache.objects.update_or_create(
                symbol=normalized_symbol,
                timeframe=timeframe,
                limit=limit,
                defaults={"payload": alpaca_bars},
            )
            return alpaca_bars
    except Exception:
        pass

    # 3. High-fidelity realistic forex candle generation
    payload = _generate_forex_candles(normalized_symbol, timeframe, limit)
    MarketDataCache.objects.update_or_create(
        symbol=normalized_symbol,
        timeframe=timeframe,
        limit=limit,
        defaults={"payload": payload},
    )
    return payload


def latest_price(symbol: str, timeframe: str = "1m") -> float:
    candles = get_candles(symbol, timeframe, limit=2)
    if not candles:
        norm = normalize_symbol(symbol)
        return FOREX_BASE_PRICES.get(norm, 1.0)
    return float(candles[-1]["close"])


def _fetch_alpaca_bars(symbol: str, timeframe: str, limit: int) -> list[dict]:
    """
    Query Alpaca Market Data v2 bars endpoint.
    """
    client = get_alpaca_client()
    timeframe_map = {
        "1m": "1Min",
        "5m": "5Min",
        "15m": "15Min",
        "1h": "1Hour",
        "4h": "4Hour",
        "1d": "1Day",
    }
    alpaca_tf = timeframe_map.get(timeframe, "1Hour")

    # Alpaca Crypto/Forex bars endpoint
    # E.g. GET /v1beta3/crypto/us/bars?symbols=BTC/USD&timeframe=1Hour&limit=500
    display_sym = format_display_symbol(symbol)
    norm = normalize_symbol(symbol)
    is_stock = len(norm) <= 5 and norm.isalpha()

    try:
        if is_stock:
            # US Stock bars endpoint: /v2/stocks/bars?symbols=AAPL&timeframe=...
            data = client._request(
                "GET",
                "/v2/stocks/bars",
                params={"symbols": norm, "timeframe": alpaca_tf, "limit": limit},
                is_data_api=True,
            )
            bars = data.get("bars", {}).get(norm, [])
        elif "/" in display_sym or "BTC" in norm or "ETH" in norm:
            data = client._request(
                "GET",
                "/v1beta3/crypto/us/bars",
                params={"symbols": display_sym, "timeframe": alpaca_tf, "limit": limit},
                is_data_api=True,
            )
            bars = data.get("bars", {}).get(display_sym, [])
        else:
            return []

        if bars:
            result = []
            for b in bars:
                result.append(
                    {
                        "time": b.get("t"),
                        "open": float(b.get("o")),
                        "high": float(b.get("h")),
                        "low": float(b.get("l")),
                        "close": float(b.get("c")),
                        "volume": float(b.get("v", 0)),
                    }
                )
            return result
    except Exception:
        pass

    return []


def _generate_forex_candles(symbol: str, timeframe: str, limit: int) -> list[dict]:
    """
    Generates realistic forex market candles with pip precision, volatility clustering,
    realistic high/low wicks, and macro trend cycles.
    """
    step_minutes = TIMEFRAME_TO_MINUTES.get(timeframe, 60)
    anchor = timezone.now().astimezone(dt_timezone.utc).replace(second=0, microsecond=0)

    # Base price from known lookup or deterministic hash
    is_jpy = "JPY" in symbol
    if symbol in FOREX_BASE_PRICES:
        base_price = FOREX_BASE_PRICES[symbol]
    else:
        seed = int(hashlib.md5(symbol.encode("utf-8")).hexdigest()[:8], 16)
        base_price = 1.05 + ((seed % 1000) / 1000.0)

    if base_price > 50:
        pip_size = 0.05
        decimals = 2
    elif is_jpy:
        pip_size = 0.01
        decimals = 3
    else:
        pip_size = 0.0001
        decimals = 5

    candles: list[dict] = []
    current_close = base_price

    # Volatility in pips per candle depending on timeframe
    vol_pips = {
        "1m": 3,
        "5m": 7,
        "15m": 14,
        "1h": 28,
        "4h": 55,
        "1d": 110,
    }.get(timeframe, 20)

    vol_unit = vol_pips * pip_size

    for index in range(limit):
        point_time = anchor - timedelta(minutes=step_minutes * (limit - index - 1))
        # Sinusoidal micro cycles + deterministic drift
        cycle1 = sin(index / 14.0) * vol_unit * 1.5
        cycle2 = cos(index / 35.0) * vol_unit * 2.2
        noise = (sin(index * 3.7) + cos(index * 1.9)) * 0.4 * vol_unit

        price_step = (cycle1 * 0.15) + (cycle2 * 0.1) + noise
        open_price = current_close
        close_price = round(open_price + price_step, decimals)

        # Realistic wicks
        body_max = max(open_price, close_price)
        body_min = min(open_price, close_price)
        upper_wick = abs(sin(index * 2.1)) * vol_unit * 0.7
        lower_wick = abs(cos(index * 2.7)) * vol_unit * 0.7

        high_price = round(body_max + upper_wick + (pip_size * 2), decimals)
        low_price = round(body_min - lower_wick - (pip_size * 2), decimals)

        volume = round(500 + abs(sin(index / 5.0)) * 1200 + (index % 11) * 45, 1)

        candles.append(
            {
                "time": point_time.isoformat(),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )
        current_close = close_price

    return candles
