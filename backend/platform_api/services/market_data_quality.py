"""Provider-agnostic validation for canonical historical OHLCV candles."""
from datetime import datetime, timezone
import math


class MarketDataQualityError(ValueError):
    """Raised when a candle batch is not safe for research use."""


def _parse_time(candle, index):
    value = candle.get("time")
    if value is None and candle.get("timestamp") is not None:
        value = candle["timestamp"]
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            raise MarketDataQualityError(f"Candle {index} has an invalid timestamp.")
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        raise MarketDataQualityError(f"Candle {index} is missing its timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketDataQualityError(f"Candle {index} has an invalid timestamp.") from exc
    if parsed.tzinfo is None:
        raise MarketDataQualityError(f"Candle {index} timestamp must include a timezone.")
    return parsed


def validate_candles(candles):
    """Validate non-empty OHLCV data without silently repairing or dropping bars."""
    if not isinstance(candles, list) or not candles:
        raise MarketDataQualityError("A non-empty candle list is required.")

    previous_time = None
    sources = set()
    for index, candle in enumerate(candles):
        if not isinstance(candle, dict):
            raise MarketDataQualityError(f"Candle {index} must be an object.")

        values = {}
        for field in ("open", "high", "low", "close", "volume"):
            try:
                value = float(candle[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise MarketDataQualityError(
                    f"Candle {index} has an invalid {field} value."
                ) from exc
            if not math.isfinite(value):
                raise MarketDataQualityError(
                    f"Candle {index} has a non-finite {field} value."
                )
            values[field] = value

        prices = [values[name] for name in ("open", "high", "low", "close")]
        if min(prices) <= 0:
            raise MarketDataQualityError(f"Candle {index} prices must be positive.")
        if values["volume"] < 0:
            raise MarketDataQualityError(f"Candle {index} volume cannot be negative.")
        if values["high"] < max(values["open"], values["close"], values["low"]):
            raise MarketDataQualityError(f"Candle {index} high violates OHLC geometry.")
        if values["low"] > min(values["open"], values["close"], values["high"]):
            raise MarketDataQualityError(f"Candle {index} low violates OHLC geometry.")

        candle_time = _parse_time(candle, index)
        if previous_time is not None and candle_time <= previous_time:
            raise MarketDataQualityError(
                "Candle timestamps must be strictly increasing without duplicates."
            )
        previous_time = candle_time
        sources.add(str(candle.get("source", "unknown")))

    return {
        "valid": True,
        "count": len(candles),
        "first_time": candles[0].get("time", candles[0].get("timestamp")),
        "last_time": candles[-1].get("time", candles[-1].get("timestamp")),
        "source": next(iter(sources)) if len(sources) == 1 else "mixed",
    }
