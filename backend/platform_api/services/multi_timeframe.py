import logging
from typing import Any

from .indicators import analyze_forex_confluence
from .market_data import format_display_symbol, latest_price, normalize_symbol

logger = logging.getLogger(__name__)


class MultiTimeframeService:
    """
    Executes top-down multi-timeframe analysis across H4, H1, and M15 time horizons:
    1. Higher Timeframe (4H): Macro Structural Trend (Directional Anchor).
    2. Intermediate Timeframe (1H): Structural Momentum & Key Dynamic Levels.
    3. Lower Timeframe (15M): Precision Entry Trigger & Execution Pullback.
    
    Strict Rule: Lower timeframe signals that contradict Higher timeframe macro trend
    are strictly rejected as high-risk counter-trend traps.
    """

    @classmethod
    def analyze_top_down(cls, symbol: str) -> dict[str, Any]:
        disp_sym = format_display_symbol(symbol)
        norm_sym = normalize_symbol(symbol)

        # 1. Higher Timeframe Analysis (4H) - Macro Trend Anchor
        h4_analysis = analyze_forex_confluence(disp_sym, timeframe="4h")
        h4_direction = h4_analysis["direction"]  # "long" | "short" | "neutral"
        h4_indicators = h4_analysis["indicators"]
        h4_price = h4_analysis["current_price"]

        # Macro bias assessment
        h4_is_bullish = h4_price > h4_indicators["ema200"] and h4_indicators["ema50"] >= h4_indicators["ema200"]
        h4_is_bearish = h4_price < h4_indicators["ema200"] and h4_indicators["ema50"] <= h4_indicators["ema200"]

        if h4_is_bullish:
            macro_bias = "BULLISH"
        elif h4_is_bearish:
            macro_bias = "BEARISH"
        else:
            macro_bias = "CONSOLIDATION"

        # 2. Intermediate Timeframe Analysis (1H) - Momentum Confirmation
        h1_analysis = analyze_forex_confluence(disp_sym, timeframe="1h")
        h1_direction = h1_analysis["direction"]
        h1_indicators = h1_analysis["indicators"]

        # 3. Lower Timeframe Analysis (15M) - Entry Trigger
        m15_analysis = analyze_forex_confluence(disp_sym, timeframe="15m")
        m15_direction = m15_analysis["direction"]
        m15_indicators = m15_analysis["indicators"]

        # 4. Top-Down Institutional Confluence Check
        is_aligned = False
        rejection_reason = None
        confluence_quality = "POOR"
        composite_score = 30.0

        if macro_bias == "BULLISH":
            if m15_direction == "long" and h1_direction in ("long", "neutral"):
                is_aligned = True
                confluence_quality = "EXCELLENT" if h1_direction == "long" else "GOOD"
                composite_score = 88.0 if h1_direction == "long" else 72.0
            elif m15_direction == "short":
                is_aligned = False
                rejection_reason = "COUNTER-TREND TRAP: M15 Short entry directly contradicts the 4-Hour Bullish macro trend. Longs only permitted."
                confluence_quality = "CONFLICTED"
                composite_score = 35.0
            else:
                is_aligned = False
                rejection_reason = "WAITING FOR PULLBACK TRIGGER: Macro trend is Bullish, but M15 trigger has not confirmed entry."
                confluence_quality = "WAITING"
                composite_score = 50.0

        elif macro_bias == "BEARISH":
            if m15_direction == "short" and h1_direction in ("short", "neutral"):
                is_aligned = True
                confluence_quality = "EXCELLENT" if h1_direction == "short" else "GOOD"
                composite_score = 88.0 if h1_direction == "short" else 72.0
            elif m15_direction == "long":
                is_aligned = False
                rejection_reason = "COUNTER-TREND TRAP: M15 Long entry directly contradicts the 4-Hour Bearish macro trend. Shorts only permitted."
                confluence_quality = "CONFLICTED"
                composite_score = 35.0
            else:
                is_aligned = False
                rejection_reason = "WAITING FOR PULLBACK TRIGGER: Macro trend is Bearish, but M15 trigger has not confirmed entry."
                confluence_quality = "WAITING"
                composite_score = 50.0

        else:
            is_aligned = False
            rejection_reason = "MARKET CONSOLIDATION: 4-Hour timeframe lacks clear directional momentum. Avoid trading chop."
            confluence_quality = "RANGING"
            composite_score = 42.0

        # Suggested execution setup if aligned
        suggested_side = "buy" if (is_aligned and macro_bias == "BULLISH") else ("sell" if (is_aligned and macro_bias == "BEARISH") else None)

        is_crypto = any(c in norm_sym for c in ("BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB", "XAU", "XAG"))
        atr_raw = m15_indicators.get("atr", 0.0015)
        atr_display = f"${atr_raw:.2f}" if is_crypto else f"{m15_analysis['atr_pips']} pips"

        if is_aligned and suggested_side:
            from .market_data import get_forex_quote
            quote = get_forex_quote(disp_sym)
            bid = quote["bid"]
            ask = quote["ask"]
            decimals = 2 if (is_crypto and bid >= 10.0) else (4 if is_crypto else (3 if "JPY" in norm_sym else 5))
            min_sl_dist = ask * 0.005 if is_crypto else (0.10 if "JPY" in norm_sym else 0.0010)
            sl_dist = max(atr_raw * 1.5, min_sl_dist)

            if suggested_side == "buy":
                entry_price = ask  # Long orders execute at the Ask
                sl = round(entry_price - sl_dist, decimals)
                tp = round(entry_price + (sl_dist * 2.0), decimals)  # True 2.0R measured from execution fill
            else:
                entry_price = bid  # Short orders execute at the Bid
                sl = round(entry_price + sl_dist, decimals)
                tp = round(entry_price - (sl_dist * 2.0), decimals)  # True 2.0R measured from execution fill
            rr_ratio = 2.0
        else:
            entry_price = None
            sl = None
            tp = None
            rr_ratio = 0.0

        return {
            "symbol": disp_sym,
            "normalized_symbol": norm_sym,
            "macro_bias_4h": macro_bias,
            "h4": {
                "direction": h4_direction,
                "confidence_pct": h4_analysis["confidence_pct"],
                "price": h4_price,
                "ema200": h4_indicators["ema200"],
                "ema50": h4_indicators["ema50"],
                "rsi": h4_indicators["rsi"],
            },
            "h1": {
                "direction": h1_direction,
                "confidence_pct": h1_analysis["confidence_pct"],
                "rsi": h1_indicators["rsi"],
                "macd_histogram": h1_indicators.get("macd_hist", 0.0),
            },
            "m15": {
                "direction": m15_direction,
                "confidence_pct": m15_analysis["confidence_pct"],
                "rsi": m15_indicators["rsi"],
                "atr_display": atr_display,
                "atr_pips": m15_analysis["atr_pips"],
            },
            "is_aligned": is_aligned,
            "confluence_quality": confluence_quality,
            "composite_score": composite_score,
            "rejection_reason": rejection_reason,
            "suggested_side": suggested_side,
            "entry_price": entry_price,
            "stop_loss": sl,
            "take_profit": tp,
            "rr_ratio": rr_ratio,
        }
