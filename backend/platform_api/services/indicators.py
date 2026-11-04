from math import sqrt
from typing import Any, Optional

from .market_data import format_display_symbol, get_candles, latest_price, normalize_symbol


def calculate_sma(data: list[float], period: int) -> list[float]:
    output: list[float] = []
    for index, _ in enumerate(data):
        if index < period - 1:
            output.append(float("nan"))
            continue
        window = data[index - period + 1 : index + 1]
        output.append(sum(window) / period)
    return output


def calculate_ema(data: list[float], period: int) -> list[float]:
    output: list[float] = []
    multiplier = 2 / (period + 1)
    for index, price in enumerate(data):
        if index == 0:
            output.append(price)
            continue
        previous = output[index - 1]
        output.append((price - previous) * multiplier + previous)
    return output


def calculate_rsi(data: list[float], period: int = 14) -> list[float]:
    output = [float("nan")] * len(data)
    if len(data) <= period:
        return output

    average_gain = 0.0
    average_loss = 0.0
    for index in range(1, period + 1):
        diff = data[index] - data[index - 1]
        if diff >= 0:
            average_gain += diff
        else:
            average_loss += abs(diff)

    average_gain /= period
    average_loss /= period
    output[period] = _rsi_value(average_gain, average_loss)

    for index in range(period + 1, len(data)):
        diff = data[index] - data[index - 1]
        gain = diff if diff > 0 else 0
        loss = abs(diff) if diff < 0 else 0
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period
        output[index] = _rsi_value(average_gain, average_loss)

    return output


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def calculate_bollinger_bands(
    data: list[float], period: int = 20, multiplier: float = 2.0
) -> tuple[list[float], list[float], list[float]]:
    middle = calculate_sma(data, period)
    upper = [float("nan")] * len(data)
    lower = [float("nan")] * len(data)

    for index in range(period - 1, len(data)):
        average = middle[index]
        window = data[index - period + 1 : index + 1]
        variance = sum((value - average) ** 2 for value in window) / period
        standard_deviation = sqrt(variance)
        upper[index] = average + standard_deviation * multiplier
        lower[index] = average - standard_deviation * multiplier

    return middle, upper, lower


def calculate_macd(
    data: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float], list[float]]:
    ema_fast = calculate_ema(data, fast)
    ema_slow = calculate_ema(data, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = calculate_ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


def calculate_atr(candles: list[dict], period: int = 14) -> list[float]:
    """Average True Range for volatility & position sizing."""
    if len(candles) < 2:
        return [0.0] * len(candles)

    true_ranges = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        l = candles[i]["low"]
        prev_c = candles[i - 1]["close"]
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        true_ranges.append(tr)

    atr = calculate_sma(true_ranges, period)
    return atr


def analyze_forex_confluence(
    symbol: str, timeframe: str = "1h", candles: Optional[list[dict]] = None
) -> dict[str, Any]:
    """
    Live-scanner wrapper around the canonical trend/breakout module.

    Signal direction/confidence/indicators come from
    trend_breakout.score_single_timeframe (completed bars only, no lookahead).
    Live price is used only for display and SL/TP placement around the signal.
    """
    norm_sym = normalize_symbol(symbol)
    disp_sym = format_display_symbol(symbol)

    if candles is None or len(candles) < 30:
        candles = get_candles(norm_sym, timeframe=timeframe, limit=300)

    closes = [float(c["close"]) for c in candles]
    live_px = latest_price(norm_sym)
    close_px = closes[-1]
    curr_price = float(live_px) if live_px else close_px

    # Canonical signal on completed bars (single source of truth).
    from .trend_breakout import (
        REWARD_RISK_MULTIPLE,
        ATR_STOP_MULTIPLIER,
        classify_symbol,
        score_single_timeframe,
    )

    pure = score_single_timeframe(candles, symbol=norm_sym)
    spec = classify_symbol(norm_sym, curr_price)
    decimals = spec["decimals"]
    is_crypto = spec["is_crypto"]
    is_jpy = spec["is_jpy"]
    pip_multiplier = 1.0 if is_crypto else (100.0 if is_jpy else 10000.0)
    curr_atr = float(pure["atr"])
    atr_pips = round(curr_atr * pip_multiplier, 1)
    direction = pure["direction"]
    confidence = pure["confidence"]
    reasons = pure["reasons"]
    ind = pure["indicators"]
    curr_rsi = ind["rsi"]
    curr_ema20 = ind["ema20"]
    curr_ema50 = ind["ema50"]
    curr_ema200 = ind["ema200"]
    curr_macd = ind["macd"]
    curr_sig = ind["macd_signal"]
    curr_hist = ind["macd_hist"]
    curr_bb_upper = ind["bb_upper"]
    curr_bb_lower = ind["bb_lower"]
    if direction == "long":
        side = "buy"
        sl_distance = max(curr_atr * ATR_STOP_MULTIPLIER, spec["min_sl_distance"])
        stop_loss = round(curr_price - sl_distance, decimals)
        take_profit = round(curr_price + sl_distance * REWARD_RISK_MULTIPLE, decimals)
    elif direction == "short":
        side = "sell"
        sl_distance = max(curr_atr * ATR_STOP_MULTIPLIER, spec["min_sl_distance"])
        stop_loss = round(curr_price + sl_distance, decimals)
        take_profit = round(curr_price - sl_distance * REWARD_RISK_MULTIPLE, decimals)
    else:
        side = "hold"
        stop_loss = None
        take_profit = None

    return {
        "symbol": disp_sym,
        "timeframe": timeframe,
        "current_price": curr_price,
        "direction": direction,
        "suggested_side": side,
        "confidence": confidence,
        "confidence_pct": round(confidence * 100.0, 1),
        "trigger_type": pure.get("trigger_type", "none"),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr_ratio": REWARD_RISK_MULTIPLE if stop_loss else 0.0,
        "atr_pips": atr_pips,
        "reasons": reasons,
        "indicators": {
            "rsi": curr_rsi,
            "ema20": curr_ema20,
            "ema50": curr_ema50,
            "ema200": curr_ema200,
            "macd": curr_macd,
            "macd_signal": curr_sig,
            "macd_hist": curr_hist,
            "atr": round(curr_atr, decimals + 1),
            "bb_upper": curr_bb_upper,
            "bb_lower": curr_bb_lower,
        },
        "candles_series": candles,
    }



