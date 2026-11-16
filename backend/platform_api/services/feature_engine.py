"""Versioned causal features for historical market research.

Every value at index i is calculated from candle indices <= i only. This
module is deterministic and pure: it has no database, provider or broker calls.
"""
from datetime import datetime, timezone
import math
from statistics import mean

from .market_data_quality import validate_candles


FEATURE_SET_VERSION = "1.0.0"
FEATURE_REQUIRED_BARS = 200
RETURN_PERIODS = (1, 3, 6, 12)


def _number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Feature inputs must be finite numbers.")
    return result


def _timestamp_iso(candle):
    value = candle.get("time", candle.get("timestamp"))
    if isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).isoformat()


def _ema(values, period):
    """EMA with an SMA seed; no value exists until period bars are available."""
    output = [None] * len(values)
    if len(values) < period:
        return output

    current = mean(values[:period])
    output[period - 1] = current
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        current = (values[index] * alpha) + (current * (1.0 - alpha))
        output[index] = current
    return output


def _wilder_rsi(closes, period=14):
    output = [None] * len(closes)
    if len(closes) <= period:
        return output

    gains = []
    losses = []
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = mean(gains)
    average_loss = mean(losses)

    def rsi_value(gain, loss):
        if loss == 0:
            return 100.0 if gain > 0 else 50.0
        relative_strength = gain / loss
        return 100.0 - (100.0 / (1.0 + relative_strength))

    output[period] = rsi_value(average_gain, average_loss)
    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        average_gain = ((average_gain * (period - 1)) + gain) / period
        average_loss = ((average_loss * (period - 1)) + loss) / period
        output[index] = rsi_value(average_gain, average_loss)
    return output


def _true_ranges(highs, lows, closes):
    output = []
    for index in range(len(highs)):
        if index == 0:
            output.append(highs[index] - lows[index])
        else:
            output.append(max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            ))
    return output


def _wilder_atr(true_ranges, period=14):
    output = [None] * len(true_ranges)
    if len(true_ranges) < period:
        return output

    current = mean(true_ranges[:period])
    output[period - 1] = current
    for index in range(period, len(true_ranges)):
        current = ((current * (period - 1)) + true_ranges[index]) / period
        output[index] = current
    return output


def _rolling_mean_std(values, period, start_index=0):
    means = [None] * len(values)
    stds = [None] * len(values)
    for index in range(start_index + period - 1, len(values)):
        window = values[index - period + 1:index + 1]
        average = mean(window)
        variance = mean([(value - average) ** 2 for value in window])
        means[index] = average
        stds[index] = math.sqrt(max(variance, 0.0))
    return means, stds


def _safe_ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator) * 100.0


def build_feature_series(
    candles,
    symbol=None,
    timeframe=None,
    spread_pips=None,
    pip_size=None,
):
    """Build causal per-bar features and a latest-bar summary.

    spread_pips and pip_size are optional explicit inputs. If absent, cost
    features remain null rather than inventing a spread assumption.
    """
    validation = validate_candles(candles)
    if (spread_pips is None) != (pip_size is None):
        raise ValueError("spread_pips and pip_size must be supplied together.")

    if spread_pips is not None:
        spread_pips = _number(spread_pips)
        pip_size = _number(pip_size)
        if spread_pips < 0 or pip_size <= 0:
            raise ValueError("spread_pips must be non-negative and pip_size must be positive.")

    opens = [_number(candle["open"]) for candle in candles]
    highs = [_number(candle["high"]) for candle in candles]
    lows = [_number(candle["low"]) for candle in candles]
    closes = [_number(candle["close"]) for candle in candles]
    volumes = [_number(candle["volume"]) for candle in candles]
    count = len(candles)

    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    rsi14 = _wilder_rsi(closes, 14)
    true_ranges = _true_ranges(highs, lows, closes)
    atr14 = _wilder_atr(true_ranges, 14)
    volume_mean20, volume_std20 = _rolling_mean_std(volumes, 20)
    close_mean20, close_std20 = _rolling_mean_std(closes, 20)

    return_series = {
        period: [
            None if index < period else ((closes[index] / closes[index - period]) - 1.0) * 100.0
            for index in range(count)
        ]
        for period in RETURN_PERIODS
    }
    _, return_stds = _rolling_mean_std(return_series[1], 20, start_index=1)

    rows = []
    for index, candle in enumerate(candles):
        current_close = closes[index]
        feature_values = {
            "return1Pct": return_series[1][index],
            "return3Pct": return_series[3][index],
            "return6Pct": return_series[6][index],
            "return12Pct": return_series[12][index],
            "ema20": ema20[index],
            "ema50": ema50[index],
            "ema200": ema200[index],
            "ema20Vs50Pct": (
                ((ema20[index] / ema50[index]) - 1.0) * 100.0
                if ema20[index] is not None and ema50[index] not in (None, 0)
                else None
            ),
            "ema50Vs200Pct": (
                ((ema50[index] / ema200[index]) - 1.0) * 100.0
                if ema50[index] is not None and ema200[index] not in (None, 0)
                else None
            ),
            "closeVsEma200Pct": (
                ((current_close / ema200[index]) - 1.0) * 100.0
                if ema200[index] not in (None, 0)
                else None
            ),
            "rsi14": rsi14[index],
            "atr14": atr14[index],
            "atrPct": _safe_ratio(atr14[index], current_close),
            "volatility20Pct": return_stds[index],
            "bollingerWidth20Pct": (
                (4.0 * close_std20[index] / close_mean20[index]) * 100.0
                if close_std20[index] is not None and close_mean20[index] not in (None, 0)
                else None
            ),
            "volumeZScore20": (
                (volumes[index] - volume_mean20[index]) / volume_std20[index]
                if volume_mean20[index] is not None and volume_std20[index] not in (None, 0)
                else (0.0 if volume_std20[index] == 0 else None)
            ),
            "candleRangePct": ((highs[index] - lows[index]) / current_close) * 100.0,
            "candleBodyPct": (abs(current_close - opens[index]) / opens[index]) * 100.0,
            "signedCandleBodyPct": ((current_close - opens[index]) / opens[index]) * 100.0,
            "closeLocation": (
                (current_close - lows[index]) / (highs[index] - lows[index])
                if highs[index] > lows[index]
                else None
            ),
            "spreadPips": spread_pips,
            "spreadCostPct": (
                ((spread_pips * pip_size) / current_close) * 100.0
                if spread_pips is not None
                else None
            ),
        }
        rows.append({
            "index": index,
            "time": _timestamp_iso(candle),
            "features": feature_values,
        })

    latest = rows[-1]["features"]
    ready = count >= FEATURE_REQUIRED_BARS and all(
        latest[field] is not None
        for field in (
            "ema20", "ema50", "ema200", "rsi14", "atr14",
            "volatility20Pct", "bollingerWidth20Pct", "volumeZScore20",
            "return12Pct",
        )
    )
    return {
        "featureSetVersion": FEATURE_SET_VERSION,
        "featureDefinitions": {
            "ema": "SMA-seeded exponential moving average",
            "rsi14": "Wilder RSI, seeded from the first 14 close-to-close changes",
            "atr14": "Wilder ATR, seeded from the first 14 true ranges",
            "volatility20Pct": "Population standard deviation of the latest 20 one-bar percentage returns",
            "bollingerWidth20Pct": "Four population standard deviations divided by the 20-bar mean, expressed as percent",
            "volumeZScore20": "Population z-score of current volume against the trailing 20 bars, including the current bar",
            "spreadCostPct": "Explicit quoted spread in price units divided by close, expressed as percent; null unless spread and pip size are supplied",
            "causality": "Every feature row uses only that row and earlier candles",
        },
        "symbol": symbol,
        "timeframe": timeframe,
        "source": validation["source"],
        "asOf": rows[-1]["time"],
        "barCount": count,
        "requiredBars": FEATURE_REQUIRED_BARS,
        "warmupBars": max(FEATURE_REQUIRED_BARS - count, 0),
        "ready": ready,
        "abstainReason": None if ready else "insufficient_history",
        "latest": latest,
        "series": rows,
    }
