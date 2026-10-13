import logging
from typing import Any

from .indicators import analyze_forex_confluence
from .market_data import format_display_symbol, latest_price, normalize_symbol

logger = logging.getLogger(__name__)


class MultiTimeframeService:
    """
    Executes top-down multi-timeframe analysis.

    Two modes are supported:

    SWING (default / institutional):
        4H → Macro structural anchor (hard veto)
        1H → Momentum confirmation
        15M → Entry trigger

    INTRADAY:
        4H → Awareness context only (soft, no veto)
        1H → Macro structural anchor
        15M → Entry trigger

    The mode is passed via the `mode` parameter ("swing" | "intraday").
    """

    @classmethod
    def analyze_top_down(cls, symbol: str, mode: str = "swing") -> dict[str, Any]:
        mode = mode.lower().strip()
        if mode not in ("swing", "intraday"):
            mode = "swing"

        disp_sym = format_display_symbol(symbol)
        norm_sym = normalize_symbol(symbol)

        # ── Always fetch all three timeframes (used for context in both modes) ──
        h4_analysis = analyze_forex_confluence(disp_sym, timeframe="4h")
        h4_direction = h4_analysis["direction"]
        h4_indicators = h4_analysis["indicators"]
        h4_price = h4_analysis["current_price"]

        h1_analysis = analyze_forex_confluence(disp_sym, timeframe="1h")
        h1_direction = h1_analysis["direction"]
        h1_indicators = h1_analysis["indicators"]

        m15_analysis = analyze_forex_confluence(disp_sym, timeframe="15m")
        m15_direction = m15_analysis["direction"]
        m15_indicators = m15_analysis["indicators"]

        # ── 4H macro bias (used as anchor in swing, awareness-only in intraday) ──
        h4_is_bullish = (
            h4_price > h4_indicators["ema200"]
            and h4_indicators["ema50"] >= h4_indicators["ema200"]
        )
        h4_is_bearish = (
            h4_price < h4_indicators["ema200"]
            and h4_indicators["ema50"] <= h4_indicators["ema200"]
        )
        if h4_is_bullish:
            macro_bias_4h = "BULLISH"
        elif h4_is_bearish:
            macro_bias_4h = "BEARISH"
        else:
            macro_bias_4h = "CONSOLIDATION"

        # ── Route to the correct analysis mode ──
        if mode == "intraday":
            result = cls._analyze_intraday(
                norm_sym, disp_sym,
                h1_direction, h1_indicators, h1_analysis,
                m15_direction, m15_indicators, m15_analysis,
                macro_bias_4h, h4_indicators, h4_price, h4_analysis,
            )
        else:
            result = cls._analyze_swing(
                norm_sym, disp_sym,
                macro_bias_4h,
                h1_direction, h1_indicators, h1_analysis,
                m15_direction, m15_indicators, m15_analysis,
                h4_indicators, h4_price, h4_analysis,
            )

        result["mode"] = mode
        return result

    # ─────────────────────────────────────────────────────────────────────────
    # SWING MODE  (4H anchor, 1H confirm, 15M entry)
    # ─────────────────────────────────────────────────────────────────────────
    @classmethod
    def _analyze_swing(
        cls, norm_sym, disp_sym,
        macro_bias,
        h1_direction, h1_indicators, h1_analysis,
        m15_direction, m15_indicators, m15_analysis,
        h4_indicators, h4_price, h4_analysis,
    ) -> dict[str, Any]:
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
                rejection_reason = "COUNTER-TREND TRAP: M15 Short entry directly contradicts the 4-Hour Bullish macro trend. Longs only permitted."
                confluence_quality = "CONFLICTED"
                composite_score = 35.0
            else:
                rejection_reason = "WAITING FOR PULLBACK TRIGGER: Macro trend is Bullish, but M15 trigger has not confirmed entry."
                confluence_quality = "WAITING"
                composite_score = 50.0

        elif macro_bias == "BEARISH":
            if m15_direction == "short" and h1_direction in ("short", "neutral"):
                is_aligned = True
                confluence_quality = "EXCELLENT" if h1_direction == "short" else "GOOD"
                composite_score = 88.0 if h1_direction == "short" else 72.0
            elif m15_direction == "long":
                rejection_reason = "COUNTER-TREND TRAP: M15 Long entry directly contradicts the 4-Hour Bearish macro trend. Shorts only permitted."
                confluence_quality = "CONFLICTED"
                composite_score = 35.0
            else:
                rejection_reason = "WAITING FOR PULLBACK TRIGGER: Macro trend is Bearish, but M15 trigger has not confirmed entry."
                confluence_quality = "WAITING"
                composite_score = 50.0

        else:
            rejection_reason = "MARKET CONSOLIDATION: 4-Hour timeframe lacks clear directional momentum. Avoid trading chop."
            confluence_quality = "RANGING"
            composite_score = 42.0

        suggested_side = (
            "buy" if (is_aligned and macro_bias == "BULLISH")
            else "sell" if (is_aligned and macro_bias == "BEARISH")
            else None
        )

        entry_price, sl, tp, rr_ratio = cls._build_execution(
            norm_sym, disp_sym, is_aligned, suggested_side, m15_indicators, m15_analysis
        )

        return {
            "symbol": disp_sym,
            "normalized_symbol": norm_sym,
            "macro_bias_4h": macro_bias,
            "h4": {
                "direction": h4_analysis["direction"],
                "confidence_pct": h4_analysis["confidence_pct"],
                "price": h4_price,
                "ema200": h4_indicators["ema200"],
                "ema50": h4_indicators["ema50"],
                "rsi": h4_indicators["rsi"],
                "role": "MACRO ANCHOR (hard veto)",
            },
            "h1": {
                "direction": h1_direction,
                "confidence_pct": h1_analysis["confidence_pct"],
                "rsi": h1_indicators["rsi"],
                "macd_histogram": h1_indicators.get("macd_hist", 0.0),
                "role": "CONFIRMATION",
            },
            "m15": {
                "direction": m15_direction,
                "confidence_pct": m15_analysis["confidence_pct"],
                "rsi": m15_indicators["rsi"],
                "atr_display": cls._atr_display(norm_sym, m15_indicators, m15_analysis),
                "atr_pips": m15_analysis["atr_pips"],
                "role": "ENTRY TRIGGER",
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

    # ─────────────────────────────────────────────────────────────────────────
    # INTRADAY MODE  (1H anchor, 15M entry, 4H = awareness context only)
    # ─────────────────────────────────────────────────────────────────────────
    @classmethod
    def _analyze_intraday(
        cls, norm_sym, disp_sym,
        h1_direction, h1_indicators, h1_analysis,
        m15_direction, m15_indicators, m15_analysis,
        macro_bias_4h, h4_indicators, h4_price, h4_analysis,
    ) -> dict[str, Any]:
        """
        Intraday top-down:  1H is the macro anchor.  15M is the entry trigger.
        4H provides context (contra-trend warning) but never blocks a trade.
        """
        # 1H macro bias (EMA stack on 1H chart)
        h1_price = h1_analysis["current_price"]
        h1_ema200 = h1_indicators["ema200"]
        h1_ema50 = h1_indicators["ema50"]

        h1_is_bullish = h1_price > h1_ema200 and h1_ema50 >= h1_ema200
        h1_is_bearish = h1_price < h1_ema200 and h1_ema50 <= h1_ema200

        if h1_is_bullish:
            intraday_bias = "BULLISH"
        elif h1_is_bearish:
            intraday_bias = "BEARISH"
        else:
            intraday_bias = "CONSOLIDATION"

        # 4H contra-trend awareness (soft warning only — no veto)
        h4_contra_warning = None
        if macro_bias_4h == "BEARISH" and intraday_bias == "BULLISH":
            h4_contra_warning = (
                "⚠️ 4H CONTEXT: Macro trend is BEARISH. "
                "This intraday long runs against the higher timeframe. "
                "Use tighter risk. Consider reducing position size."
            )
        elif macro_bias_4h == "BULLISH" and intraday_bias == "BEARISH":
            h4_contra_warning = (
                "⚠️ 4H CONTEXT: Macro trend is BULLISH. "
                "This intraday short runs against the higher timeframe. "
                "Use tighter risk. Consider reducing position size."
            )

        is_aligned = False
        rejection_reason = None
        confluence_quality = "POOR"
        composite_score = 30.0

        if intraday_bias == "BULLISH":
            if m15_direction == "long":
                is_aligned = True
                # Score: excellent if 4H also agrees, good if neutral, caution if against
                if macro_bias_4h == "BULLISH":
                    confluence_quality = "EXCELLENT"
                    composite_score = 92.0
                elif macro_bias_4h == "CONSOLIDATION":
                    confluence_quality = "GOOD"
                    composite_score = 75.0
                else:  # 4H bearish — tradeable but flagged
                    confluence_quality = "CAUTION"
                    composite_score = 62.0
            elif m15_direction == "short":
                rejection_reason = (
                    "COUNTER-TREND TRAP: M15 Short contradicts the 1H Bullish intraday structure. "
                    "Wait for a long pullback entry on 15M."
                )
                confluence_quality = "CONFLICTED"
                composite_score = 35.0
            else:
                rejection_reason = (
                    "WAITING: 1H trend is Bullish but 15M has not triggered a long entry yet. "
                    "Wait for 15M momentum to confirm."
                )
                confluence_quality = "WAITING"
                composite_score = 52.0

        elif intraday_bias == "BEARISH":
            if m15_direction == "short":
                is_aligned = True
                if macro_bias_4h == "BEARISH":
                    confluence_quality = "EXCELLENT"
                    composite_score = 92.0
                elif macro_bias_4h == "CONSOLIDATION":
                    confluence_quality = "GOOD"
                    composite_score = 75.0
                else:  # 4H bullish — tradeable but flagged
                    confluence_quality = "CAUTION"
                    composite_score = 62.0
            elif m15_direction == "long":
                rejection_reason = (
                    "COUNTER-TREND TRAP: M15 Long contradicts the 1H Bearish intraday structure. "
                    "Wait for a short pullback entry on 15M."
                )
                confluence_quality = "CONFLICTED"
                composite_score = 35.0
            else:
                rejection_reason = (
                    "WAITING: 1H trend is Bearish but 15M has not triggered a short entry yet. "
                    "Wait for 15M momentum to confirm."
                )
                confluence_quality = "WAITING"
                composite_score = 52.0

        else:
            rejection_reason = (
                "RANGING: 1H timeframe is in consolidation. "
                "No clear intraday direction. Avoid new entries."
            )
            confluence_quality = "RANGING"
            composite_score = 42.0

        suggested_side = (
            "buy" if (is_aligned and intraday_bias == "BULLISH")
            else "sell" if (is_aligned and intraday_bias == "BEARISH")
            else None
        )

        entry_price, sl, tp, rr_ratio = cls._build_execution(
            norm_sym, disp_sym, is_aligned, suggested_side, m15_indicators, m15_analysis
        )

        return {
            "symbol": disp_sym,
            "normalized_symbol": norm_sym,
            "macro_bias_4h": macro_bias_4h,
            "intraday_bias_1h": intraday_bias,
            "h4_contra_warning": h4_contra_warning,
            "h4": {
                "direction": h4_analysis["direction"],
                "confidence_pct": h4_analysis["confidence_pct"],
                "price": h4_price,
                "ema200": h4_indicators["ema200"],
                "ema50": h4_indicators["ema50"],
                "rsi": h4_indicators["rsi"],
                "role": "AWARENESS CONTEXT (no veto)",
            },
            "h1": {
                "direction": h1_direction,
                "confidence_pct": h1_analysis["confidence_pct"],
                "rsi": h1_indicators["rsi"],
                "ema200": h1_ema200,
                "ema50": h1_ema50,
                "macd_histogram": h1_indicators.get("macd_hist", 0.0),
                "role": "INTRADAY MACRO ANCHOR",
            },
            "m15": {
                "direction": m15_direction,
                "confidence_pct": m15_analysis["confidence_pct"],
                "rsi": m15_indicators["rsi"],
                "atr_display": cls._atr_display(norm_sym, m15_indicators, m15_analysis),
                "atr_pips": m15_analysis["atr_pips"],
                "role": "ENTRY TRIGGER",
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

    # ─────────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────────
    @classmethod
    def _atr_display(cls, norm_sym: str, m15_indicators: dict, m15_analysis: dict) -> str:
        is_crypto = any(c in norm_sym for c in ("BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB", "XAU", "XAG"))
        atr_raw = m15_indicators.get("atr", 0.0015)
        return f"${atr_raw:.2f}" if is_crypto else f"{m15_analysis['atr_pips']} pips"

    @classmethod
    def _build_execution(
        cls,
        norm_sym: str, disp_sym: str,
        is_aligned: bool, suggested_side: str | None,
        m15_indicators: dict, m15_analysis: dict,
    ) -> tuple:
        """Returns (entry_price, stop_loss, take_profit, rr_ratio)."""
        if not (is_aligned and suggested_side):
            return None, None, None, 0.0

        from .market_data import get_forex_quote
        quote = get_forex_quote(disp_sym)
        bid = quote["bid"]
        ask = quote["ask"]

        is_crypto = any(c in norm_sym for c in ("BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB", "XAU", "XAG"))
        is_jpy = "JPY" in norm_sym
        decimals = 2 if (is_crypto and bid >= 10.0) else (4 if is_crypto else (3 if is_jpy else 5))

        atr_raw = m15_indicators.get("atr", 0.0015)
        min_sl_dist = ask * 0.005 if is_crypto else (0.10 if is_jpy else 0.0010)
        sl_dist = max(atr_raw * 1.5, min_sl_dist)

        if suggested_side == "buy":
            entry_price = ask
            sl = round(entry_price - sl_dist, decimals)
            tp = round(entry_price + sl_dist * 2.0, decimals)
        else:
            entry_price = bid
            sl = round(entry_price + sl_dist, decimals)
            tp = round(entry_price - sl_dist * 2.0, decimals)

        return entry_price, sl, tp, 2.0
