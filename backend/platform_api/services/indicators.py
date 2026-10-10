from math import sqrt
from typing import Any, Optional

import numpy as np
import pandas as pd

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
    Computes a multi-indicator confluence score for a currency pair:
    - Trend: EMA 20, 50, 200
    - Momentum: RSI(14)
    - Momentum Shift: MACD line vs Signal line & Histogram
    - Volatility & Range: ATR(14) and Bollinger Bands
    - Generates dynamic SL and TP prices ensuring minimum 2.0R ratio.
    """
    norm_sym = normalize_symbol(symbol)
    disp_sym = format_display_symbol(symbol)

    if candles is None or len(candles) < 30:
        candles = get_candles(norm_sym, timeframe=timeframe, limit=120)

    closes = [float(c["close"]) for c in candles]
    live_px = latest_price(norm_sym)
    curr_price = float(live_px) if live_px else closes[-1]
    is_crypto = any(c in norm_sym for c in ("BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB", "XAU", "XAG")) or curr_price > 500
    is_jpy = "JPY" in norm_sym

    if is_crypto:
        pip_multiplier = 1.0
        decimals = 2 if curr_price >= 10.0 else 4
        default_atr = curr_price * 0.015
        min_sl_dist = curr_price * 0.005
    elif is_jpy:
        pip_multiplier = 100.0
        decimals = 3
        default_atr = 0.15
        min_sl_dist = 0.10
    else:
        pip_multiplier = 10000.0
        decimals = 5
        default_atr = 0.0015
        min_sl_dist = 0.0010

    # Technical Indicators
    rsi_vals = calculate_rsi(closes, period=14)
    curr_rsi = round(rsi_vals[-1], 2) if rsi_vals else 50.0

    ema20 = calculate_ema(closes, period=20)
    ema50 = calculate_ema(closes, period=50)
    ema200 = calculate_ema(closes, period=min(200, len(closes) - 1))

    curr_ema20 = round(ema20[-1], decimals)
    curr_ema50 = round(ema50[-1], decimals)
    curr_ema200 = round(ema200[-1], decimals)

    macd_line, sig_line, hist = calculate_macd(closes)
    curr_macd = round(macd_line[-1], decimals + 1)
    curr_sig = round(sig_line[-1], decimals + 1)
    curr_hist = round(hist[-1], decimals + 1)

    atr_vals = calculate_atr(candles, period=14)
    curr_atr = atr_vals[-1] if atr_vals and not np.isnan(atr_vals[-1]) else default_atr
    atr_pips = round(curr_atr * pip_multiplier, 1)

    _, bb_upper, bb_lower = calculate_bollinger_bands(closes, period=20, multiplier=2.0)
    curr_bb_upper = round(bb_upper[-1], decimals) if bb_upper else curr_price * 1.01
    curr_bb_lower = round(bb_lower[-1], decimals) if bb_lower else curr_price * 0.99

    # Confluence Scoring (Long vs Short points)
    long_points = 0
    short_points = 0
    reasons: list[str] = []

    # 1. EMA Trend alignment
    if curr_price > curr_ema20 > curr_ema50:
        long_points += 3
        reasons.append(f"Price ({curr_price}) is riding above EMA 20 & 50 in bullish alignment.")
    elif curr_price < curr_ema20 < curr_ema50:
        short_points += 3
        reasons.append(f"Price ({curr_price}) is suppressed below EMA 20 & 50 in bearish alignment.")

    if curr_price > curr_ema200:
        long_points += 1
        reasons.append(f"Macro trend is bullish above EMA 200 ({curr_ema200}).")
    else:
        short_points += 1
        reasons.append(f"Macro trend is bearish below EMA 200 ({curr_ema200}).")

    # 2. RSI Momentum
    if 40 <= curr_rsi <= 65 and curr_price > curr_ema20:
        long_points += 2
        reasons.append(f"RSI ({curr_rsi}) has bullish momentum without being overbought.")
    elif 35 <= curr_rsi <= 60 and curr_price < curr_ema20:
        short_points += 2
        reasons.append(f"RSI ({curr_rsi}) has bearish momentum without being oversold.")
    elif curr_rsi < 30:
        long_points += 1
        reasons.append(f"RSI ({curr_rsi}) is oversold, potential mean-reversion long.")
    elif curr_rsi > 70:
        short_points += 1
        reasons.append(f"RSI ({curr_rsi}) is overbought, potential mean-reversion short.")

    # 3. MACD Momentum
    if curr_macd > curr_sig and curr_hist > 0:
        long_points += 2
        reasons.append(f"MACD histogram ({curr_hist}) is positive and expanding upward.")
    elif curr_macd < curr_sig and curr_hist < 0:
        short_points += 2
        reasons.append(f"MACD histogram ({curr_hist}) is negative and expanding downward.")

    # 4. Bollinger Bands Positioning
    if curr_price <= curr_bb_lower * 1.002:
        long_points += 1
        reasons.append(f"Price touching lower Bollinger Band ({curr_bb_lower}), support reaction zone.")
    elif curr_price >= curr_bb_upper * 0.998:
        short_points += 1
        reasons.append(f"Price touching upper Bollinger Band ({curr_bb_upper}), resistance reaction zone.")

    # Determine Direction & Confidence
    total_score = max(long_points, short_points)
    max_possible = 9.0
    confidence = round(min(1.0, total_score / max_possible), 2)

    if long_points >= short_points + 2 and confidence >= 0.55:
        direction = "long"
        side = "buy"
        # Dynamic Stop Loss & Take Profit (1.5x ATR SL, 3.0x ATR TP = 2.0R ratio)
        sl_distance = max(curr_atr * 1.5, min_sl_dist)
        tp_distance = sl_distance * 2.0
        stop_loss = round(curr_price - sl_distance, decimals)
        take_profit = round(curr_price + tp_distance, decimals)
    elif short_points >= long_points + 2 and confidence >= 0.55:
        direction = "short"
        side = "sell"
        sl_distance = max(curr_atr * 1.5, min_sl_dist)
        tp_distance = sl_distance * 2.0
        stop_loss = round(curr_price + sl_distance, decimals)
        take_profit = round(curr_price - tp_distance, decimals)
    else:
        direction = "neutral"
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
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr_ratio": 2.0 if stop_loss else 0.0,
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
    }
