"""Single formal trend/breakout strategy module (v1).

One rule set drives scanning, backtesting, paper trading, and broker execution.

Pipeline:
    H4 trend bias -> H1 confirmation -> M15 trigger -> regime gate
    -> ATR stop/target -> risk manager -> execution.

This module is deliberately pure (no Django DB, no network) so the backtester
can execute the exact same rules the live scanner uses.
"""

from __future__ import annotations

from typing import Any

STRATEGY_ID = "trend-breakout-v1"
STRATEGY_VERSION = "1.0.0"
MIN_CONFIDENCE = 0.55
ATR_STOP_MULTIPLIER = 1.5
REWARD_RISK_MULTIPLE = 2.0

# Re-exported so callers have one import for the canonical thresholds.
DEFAULT_SETTINGS = {
    "minConfidence": MIN_CONFIDENCE,
    "atrStopMultiplier": ATR_STOP_MULTIPLIER,
    "rewardRiskMultiple": REWARD_RISK_MULTIPLE,
    "riskPct": 0.01,
    "allowShort": True,
}


def classify_symbol(symbol: str, reference_price: float = 0.0) -> dict[str, Any]:
    norm = symbol.replace("/", "").replace("_", "").replace("-", "").upper()
    is_crypto = (
        any(k in norm for k in ("BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB", "XAU", "XAG"))
        or reference_price > 500
    )
    is_jpy = "JPY" in norm
    if is_crypto:
        return {
            "is_crypto": True,
            "is_jpy": False,
            "pip_size": 1.0,
            "decimals": 2 if reference_price >= 10.0 else 4,
            "default_atr": reference_price * 0.015 if reference_price else 1.0,
            "min_sl_distance": reference_price * 0.005 if reference_price else 0.01,
        }
    if is_jpy:
        return {
            "is_crypto": False,
            "is_jpy": True,
            "pip_size": 0.01,
            "decimals": 3,
            "default_atr": 0.15,
            "min_sl_distance": 0.10,
        }
    return {
        "is_crypto": False,
        "is_jpy": False,
        "pip_size": 0.0001,
        "decimals": 5,
        "default_atr": 0.0015,
        "min_sl_distance": 0.0010,
    }


def _calculate_ema(values: list[float], period: int) -> list[float]:
    out: list[float] = []
    mult = 2 / (period + 1)
    for i, px in enumerate(values):
        if i == 0:
            out.append(px)
            continue
        out.append((px - out[-1]) * mult + out[-1])
    return out


def _calculate_rsi(values: list[float], period: int = 14) -> list[float]:
    out = [float("nan")] * len(values)
    if len(values) <= period:
        return out
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, period + 1):
        diff = values[i] - values[i - 1]
        if diff >= 0:
            avg_gain += diff
        else:
            avg_loss += abs(diff)
    avg_gain /= period
    avg_loss /= period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(period + 1, len(values)):
        diff = values[i] - values[i - 1]
        gain = diff if diff > 0 else 0.0
        loss = abs(diff) if diff < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return out


def _calculate_atr(candles: list[dict], period: int = 14) -> list[float]:
    if len(candles) < 2:
        return [0.0] * len(candles)
    trs = [candles[0]["high"] - candles[0]["low"]]
    for i in range(1, len(candles)):
        h = candles[i]["high"]
        low = candles[i]["low"]
        prev_c = candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - prev_c), abs(low - prev_c)))
    out: list[float] = []
    for i in range(len(trs)):
        if i < period - 1:
            out.append(float("nan"))
            continue
        out.append(sum(trs[i - period + 1 : i + 1]) / period)
    return out


def _sma(values: list[float], period: int) -> list[float]:
    out: list[float] = []
    for i in range(len(values)):
        if i < period - 1:
            out.append(float("nan"))
            continue
        out.append(sum(values[i - period + 1 : i + 1]) / period)
    return out


def _bollinger(values: list[float], period: int = 20, mult: float = 2.0):
    mid = _sma(values, period)
    upper = [float("nan")] * len(values)
    lower = [float("nan")] * len(values)
    for i in range(period - 1, len(values)):
        avg = mid[i]
        window = values[i - period + 1 : i + 1]
        var = sum((v - avg) ** 2 for v in window) / period
        sd = var**0.5
        upper[i] = avg + sd * mult
        lower[i] = avg - sd * mult
    return mid, upper, lower


def _macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ef = _calculate_ema(values, fast)
    es = _calculate_ema(values, slow)
    line = [f - s for f, s in zip(ef, es)]
    sig = _calculate_ema(line, signal)
    hist = [m - s for m, s in zip(line, sig)]
    return line, sig, hist


def _nan_to(value: float, fallback: float) -> float:
    try:
        if value is None or value != value:  # NaN check
            return fallback
    except Exception:
        return fallback
    return value


def score_single_timeframe(
    candles: list[dict],
    symbol: str = "EURUSD",
) -> dict[str, Any]:
    """Pure per-timeframe confluence score. Same math as the live scanner.

    Expects candles up to and including the completed signal bar.
    Returns direction long/short/neutral, confidence, ATR, SL/TP distances.
    """
    if not candles:
        raise ValueError("candles required")
    closes = [float(c["close"]) for c in candles]
    price = closes[-1]
    spec = classify_symbol(symbol, price)
    decimals = spec["decimals"]

    rsi_all = _calculate_rsi(closes, 14)
    ema20_all = _calculate_ema(closes, 20)
    ema50_all = _calculate_ema(closes, 50)
    ema200_all = _calculate_ema(closes, min(200, max(2, len(closes) - 1)))
    macd_line, sig_line, hist = _macd(closes)
    atr_all = _calculate_atr(candles, 14)
    _, bb_upper_all, bb_lower_all = _bollinger(closes, 20, 2.0)

    rsi = _nan_to(rsi_all[-1], 50.0)
    ema20 = ema20_all[-1]
    ema50 = ema50_all[-1]
    ema200 = ema200_all[-1]
    macd = macd_line[-1]
    sig = sig_line[-1]
    h = hist[-1]
    atr = _nan_to(atr_all[-1], spec["default_atr"])
    bb_u = _nan_to(bb_upper_all[-1], price * 1.01)
    bb_l = _nan_to(bb_lower_all[-1], price * 0.99)

    long_pts = 0
    short_pts = 0
    reasons: list[str] = []

    if price > ema20 > ema50:
        long_pts += 3
        reasons.append("Price above EMA20/50 bullish stack.")
    elif price < ema20 < ema50:
        short_pts += 3
        reasons.append("Price below EMA20/50 bearish stack.")

    if price > ema200:
        long_pts += 1
        reasons.append("Price above EMA200 macro trend.")
    else:
        short_pts += 1
        reasons.append("Price below EMA200 macro trend.")

    if 40 <= rsi <= 65 and price > ema20:
        long_pts += 2
        reasons.append(f"RSI {round(rsi,1)} bullish momentum, not overbought.")
    elif 35 <= rsi <= 60 and price < ema20:
        short_pts += 2
        reasons.append(f"RSI {round(rsi,1)} bearish momentum, not oversold.")
    elif rsi < 30:
        long_pts += 1
        reasons.append(f"RSI {round(rsi,1)} oversold bounce zone.")
    elif rsi > 70:
        short_pts += 1
        reasons.append(f"RSI {round(rsi,1)} overbought fade zone.")

    if macd > sig and h > 0:
        long_pts += 2
        reasons.append("MACD histogram positive.")
    elif macd < sig and h < 0:
        short_pts += 2
        reasons.append("MACD histogram negative.")

    if price <= bb_l * 1.002:
        long_pts += 1
        reasons.append("Price at lower Bollinger support.")
    elif price >= bb_u * 0.998:
        short_pts += 1
        reasons.append("Price at upper Bollinger resistance.")

    total = max(long_pts, short_pts)
    confidence = round(min(1.0, total / 9.0), 2)

    sl_dist = max(atr * ATR_STOP_MULTIPLIER, spec["min_sl_distance"])
    if long_pts >= short_pts + 2 and confidence >= MIN_CONFIDENCE:
        direction = "long"
        sl = round(price - sl_dist, decimals)
        tp = round(price + sl_dist * REWARD_RISK_MULTIPLE, decimals)
    elif short_pts >= long_pts + 2 and confidence >= MIN_CONFIDENCE:
        direction = "short"
        sl = round(price + sl_dist, decimals)
        tp = round(price - sl_dist * REWARD_RISK_MULTIPLE, decimals)
    else:
        direction = "neutral"
        sl = None
        tp = None

    return {
        "direction": direction,
        "confidence": confidence,
        "confidence_pct": round(confidence * 100.0, 1),
        "reasons": reasons,
        "atr": round(atr, decimals + 1),
        "atr_distance": round(sl_dist, decimals + 1),
        "stop_loss": sl,
        "take_profit": tp,
        "rr_ratio": REWARD_RISK_MULTIPLE if sl is not None else 0.0,
        "indicators": {
            "rsi": round(rsi, 2),
            "ema20": round(ema20, decimals),
            "ema50": round(ema50, decimals),
            "ema200": round(ema200, decimals),
            "macd": round(macd, decimals + 1),
            "macd_signal": round(sig, decimals + 1),
            "macd_hist": round(h, decimals + 1),
            "atr": round(atr, decimals + 1),
            "bb_upper": round(bb_u, decimals),
            "bb_lower": round(bb_l, decimals),
        },
        "price": price,
    }


def h4_bias(price: float, ema50: float, ema200: float) -> str:
    if price > ema200 and ema50 >= ema200:
        return "BULLISH"
    if price < ema200 and ema50 <= ema200:
        return "BEARISH"
    return "CONSOLIDATION"


def regime_for_bias(macro_bias: str) -> dict[str, str]:
    if macro_bias in ("BULLISH", "BEARISH"):
        return {"regime": "trending", "permitted": "trend-breakout only"}
    return {"regime": "ranging_or_chop", "permitted": "no new trend trade"}


def evaluate_swing_alignment(macro_bias: str, h1_direction: str, m15_direction: str) -> dict[str, Any]:
    """Canonical swing rule: H4 veto, H1 confirm, M15 trigger. Shared by scan + backtest."""
    if macro_bias == "BULLISH":
        if m15_direction == "long" and h1_direction in ("long", "neutral"):
            return {
                "is_aligned": True,
                "side": "buy",
                "quality": "EXCELLENT" if h1_direction == "long" else "GOOD",
                "score": 88.0 if h1_direction == "long" else 72.0,
                "rejection": None,
            }
        if m15_direction == "short":
            return {
                "is_aligned": False,
                "side": None,
                "quality": "CONFLICTED",
                "score": 35.0,
                "rejection": "COUNTER-TREND TRAP: M15 Short contradicts H4 Bullish trend. Longs only.",
            }
        return {
            "is_aligned": False,
            "side": None,
            "quality": "WAITING",
            "score": 50.0,
            "rejection": "WAITING FOR PULLBACK TRIGGER: H4 Bullish, M15 not confirmed.",
        }
    if macro_bias == "BEARISH":
        if m15_direction == "short" and h1_direction in ("short", "neutral"):
            return {
                "is_aligned": True,
                "side": "sell",
                "quality": "EXCELLENT" if h1_direction == "short" else "GOOD",
                "score": 88.0 if h1_direction == "short" else 72.0,
                "rejection": None,
            }
        if m15_direction == "long":
            return {
                "is_aligned": False,
                "side": None,
                "quality": "CONFLICTED",
                "score": 35.0,
                "rejection": "COUNTER-TREND TRAP: M15 Long contradicts H4 Bearish trend. Shorts only.",
            }
        return {
            "is_aligned": False,
            "side": None,
            "quality": "WAITING",
            "score": 50.0,
            "rejection": "WAITING FOR PULLBACK TRIGGER: H4 Bearish, M15 not confirmed.",
        }
    return {
        "is_aligned": False,
        "side": None,
        "quality": "RANGING",
        "score": 42.0,
        "rejection": "MARKET CONSOLIDATION: H4 lacks direction. Avoid trading chop.",
    }


def evaluate_trend_breakout(
    symbol: str,
    h4_candles: list[dict] | None,
    h1_candles: list[dict] | None,
    m15_candles: list[dict] | None,
) -> dict[str, Any]:
    """Full MTF evaluation used by live scanner. All three series are completed bars."""
    if not h4_candles or not h1_candles or not m15_candles:
        raise ValueError("H4, H1, and M15 candle series are all required.")

    h4 = score_single_timeframe(h4_candles, symbol)
    h1 = score_single_timeframe(h1_candles, symbol)
    m15 = score_single_timeframe(m15_candles, symbol)

    bias = h4_bias(h4["price"], h4["indicators"]["ema50"], h4["indicators"]["ema200"])
    align = evaluate_swing_alignment(bias, h1["direction"], m15["direction"])
    regime = regime_for_bias(bias)

    return {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "symbol": symbol,
        "macro_bias_4h": bias,
        "regime": regime["regime"],
        "permitted": regime["permitted"],
        "h4": h4,
        "h1": h1,
        "m15": m15,
        "is_aligned": align["is_aligned"],
        "side": align["side"],
        "quality": align["quality"],
        "score": align["score"],
        "rejection": align["rejection"],
        "entry_reference": m15["price"],
        "stop_loss": m15["stop_loss"] if align["is_aligned"] else None,
        "take_profit": m15["take_profit"] if align["is_aligned"] else None,
        "rr_ratio": m15["rr_ratio"] if align["is_aligned"] else 0.0,
    }


def single_timeframe_signal(
    candles_so_far: list[dict],
    symbol: str = "EURUSD",
) -> dict[str, Any]:
    """Backtest entry point when only one timeframe is available.

    Uses the same per-bar scorer, then applies the H4-style macro veto proxied
    on the same series (price vs EMA200). This keeps single-TF research
    consistent with MTF live rules instead of a separate EMA-crossover system.
    """
    sig = score_single_timeframe(candles_so_far, symbol)
    bias = h4_bias(sig["price"], sig["indicators"]["ema50"], sig["indicators"]["ema200"])
    # Full regime classification on the same series (single source with live).
    try:
        from .regime import classify_regime

        closes_all = [float(c["close"]) for c in candles_so_far]
        ema50_series = _calculate_ema(closes_all, 50)
        atr_series_raw = _calculate_atr(candles_so_far, 14)
        atr_series = [v for v in atr_series_raw if v == v]
        spec = classify_symbol(symbol, sig["price"])
        reg = classify_regime(
            ema20=sig["indicators"]["ema20"],
            ema50=sig["indicators"]["ema50"],
            ema200=sig["indicators"]["ema200"],
            price=sig["price"],
            atr=sig["atr"],
            atr_series=atr_series,
            ema50_series=ema50_series,
            pip_size=spec["pip_size"],
        )
        regime_name = reg["regime"]
        regime_detail = reg
    except Exception:
        regime_name = regime_for_bias(bias)["regime"]
        regime_detail = {"regime": regime_name, "permitted": "trend-breakout only"}

    # Permission gate: trend votes only count in trending regime.
    allowed_side = None
    if regime_name == "trending":
        if sig["direction"] == "long" and bias == "BULLISH":
            allowed_side = "buy"
        elif sig["direction"] == "short" and bias == "BEARISH":
            allowed_side = "sell"

    return {
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "direction": sig["direction"],
        "side": allowed_side,
        "is_aligned": allowed_side is not None,
        "confidence": sig["confidence"],
        "macro_bias": bias,
        "regime": regime_name,
        "regime_detail": regime_detail,
        "price": sig["price"],
        "atr": sig["atr"],
        "atr_distance": sig["atr_distance"],
        "stop_loss": sig["stop_loss"],
        "take_profit": sig["take_profit"],
        "indicators": sig["indicators"],
        "reasons": sig["reasons"],
        "votes": compute_votes(candles_so_far, symbol),
    }


def donchian_break(candles: list[dict], lookback: int = 20) -> dict[str, Any]:
    """Donchian-20 range break on completed bars. Pure, no lookahead."""
    if len(candles) < lookback + 1:
        return {"break": None, "upper": None, "lower": None, "range_atr": 0.0}
    window = candles[-(lookback + 1) : -1]
    upper = max(float(c["high"]) for c in window)
    lower = min(float(c["low"]) for c in window)
    close = float(candles[-1]["close"])
    if close > upper:
        return {"break": "up", "upper": upper, "lower": lower, "range_atr": upper - lower}
    if close < lower:
        return {"break": "down", "upper": upper, "lower": lower, "range_atr": upper - lower}
    return {"break": None, "upper": upper, "lower": lower, "range_atr": upper - lower}


def compute_votes(candles: list[dict], symbol: str = "EURUSD") -> dict[str, Any]:
    """Independent vote tally: trend / momentum / breakout / mean_reversion.

    Each vote is testable alone. Never blend mean-reversion into trend.
    """
    sig = score_single_timeframe(candles, symbol)
    closes = [float(c["close"]) for c in candles]
    price = sig["price"]
    ind = sig["indicators"]
    bias = h4_bias(price, ind["ema50"], ind["ema200"])

    trend_vote = None
    if bias == "BULLISH" and sig["direction"] == "long":
        trend_vote = "buy"
    elif bias == "BEARISH" and sig["direction"] == "short":
        trend_vote = "sell"

    # Momentum: EMA9/21 cross on this series + RSI/MACD agree.
    ema9 = _calculate_ema(closes, 9)
    ema21 = _calculate_ema(closes, 21)
    momentum_vote = None
    if len(closes) >= 3:
        crossed_up = ema9[-1] > ema21[-1] and ema9[-2] <= ema21[-2]
        crossed_dn = ema9[-1] < ema21[-1] and ema9[-2] >= ema21[-2]
        rsi_ok_long = 40 <= ind["rsi"] <= 68
        rsi_ok_short = 32 <= ind["rsi"] <= 60
        macd_ok_long = ind["macd_hist"] > 0
        macd_ok_short = ind["macd_hist"] < 0
        if (crossed_up or (ema9[-1] > ema21[-1] and rsi_ok_long and macd_ok_long)) and bias == "BULLISH":
            momentum_vote = "buy"
        elif (crossed_dn or (ema9[-1] < ema21[-1] and rsi_ok_short and macd_ok_short)) and bias == "BEARISH":
            momentum_vote = "sell"

    # Breakout: Donchian-20 close beyond range in bias direction.
    dc = donchian_break(candles, 20)
    breakout_vote = None
    if dc["break"] == "up" and bias == "BULLISH":
        breakout_vote = "buy"
    elif dc["break"] == "down" and bias == "BEARISH":
        breakout_vote = "sell"

    # Mean-reversion: recorded separately, never auto-combined with trend.
    mr_vote = None
    if ind["rsi"] < 30 and price <= ind["bb_lower"] * 1.002:
        mr_vote = "buy_mr"
    elif ind["rsi"] > 70 and price >= ind["bb_upper"] * 0.998:
        mr_vote = "sell_mr"

    votes_for_buy = sum(v == "buy" for v in (trend_vote, momentum_vote, breakout_vote))
    votes_for_sell = sum(v == "sell" for v in (trend_vote, momentum_vote, breakout_vote))

    return {
        "trend": trend_vote,
        "momentum": momentum_vote,
        "breakout": breakout_vote,
        "mean_reversion": mr_vote,
        "buy_votes": votes_for_buy,
        "sell_votes": votes_for_sell,
        "donchian": dc,
        "bias": bias,
    }
