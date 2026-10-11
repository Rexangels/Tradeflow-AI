"""
Alignment Scanner Service
=========================
Scans multiple pairs simultaneously and returns a condensed
confluence summary. Designed for the real-time alert panel.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .market_data import get_forex_quote, format_display_symbol
from .multi_timeframe import MultiTimeframeService

logger = logging.getLogger(__name__)

# All crypto pairs available on Exness MT5 + popular forex
DEFAULT_SCAN_UNIVERSE = [
    "BTC/USD",
    "ETH/USD",
    "XRP/USD",
    "LTC/USD",
    "SOL/USD",
]


def _scan_single(symbol: str) -> dict[str, Any]:
    """
    Scan one symbol and return a lightweight alignment summary.
    Errors are caught and returned as a failed status so one bad
    symbol does not kill the whole scan.
    """
    try:
        mtf = MultiTimeframeService.analyze_top_down(symbol)
        quote = get_forex_quote(format_display_symbol(symbol))

        if mtf["is_aligned"]:
            alert = "TRADEABLE"
        elif mtf["confluence_quality"] == "WAITING":
            alert = "PENDING"
        elif mtf["confluence_quality"] == "CONFLICTED":
            alert = "CONFLICTED"
        else:
            alert = "RANGING"

        return {
            "symbol": mtf["symbol"],
            "alert": alert,
            "macro_bias": mtf["macro_bias_4h"],
            "h4_rsi": mtf["h4"]["rsi"],
            "h4_ema200": mtf["h4"]["ema200"],
            "h1_direction": mtf["h1"]["direction"],
            "h1_rsi": mtf["h1"]["rsi"],
            "m15_direction": mtf["m15"]["direction"],
            "m15_rsi": mtf["m15"]["rsi"],
            "confluence_quality": mtf["confluence_quality"],
            "composite_score": mtf["composite_score"],
            "is_aligned": mtf["is_aligned"],
            "suggested_side": mtf["suggested_side"],
            "entry_price": mtf["entry_price"],
            "stop_loss": mtf["stop_loss"],
            "take_profit": mtf["take_profit"],
            "rr_ratio": mtf["rr_ratio"],
            "rejection_reason": mtf["rejection_reason"],
            "bid": quote.get("bid"),
            "ask": quote.get("ask"),
            "spread": quote.get("spread_pips"),
            "ok": True,
        }
    except Exception as exc:
        logger.warning("AlignmentScanner: failed to scan %s - %s", symbol, exc)
        return {
            "symbol": symbol,
            "alert": "ERROR",
            "macro_bias": "NEUTRAL",
            "confluence_quality": "ERROR",
            "composite_score": 0.0,
            "is_aligned": False,
            "suggested_side": "HOLD",
            "ok": False,
            "error": str(exc),
        }


class AlignmentScannerService:
    """
    Scan a list of symbols and return:
    - Full per-symbol confluence data
    - A headline opportunities list (only TRADEABLE symbols)
    - Aggregate stats
    """

    @classmethod
    def scan(cls, symbols: list | None = None) -> dict[str, Any]:
        universe = symbols or DEFAULT_SCAN_UNIVERSE

        results: list[dict[str, Any]] = []

        # Scan symbols cleanly sequentially to prevent SQLite lockups in single-file DB
        for sym in universe:
            results.append(_scan_single(sym))

        def sort_key(r: dict) -> tuple:
            priority = {"TRADEABLE": 0, "PENDING": 1, "CONFLICTED": 2, "RANGING": 3, "ERROR": 4}
            return (priority.get(r.get("alert", "ERROR"), 4), -(r.get("composite_score") or 0))

        results.sort(key=sort_key)

        opportunities = [r for r in results if r.get("alert") == "TRADEABLE"]
        pending = [r for r in results if r.get("alert") == "PENDING"]
        conflicted = [r for r in results if r.get("alert") == "CONFLICTED"]

        return {
            "scanned_count": len(universe),
            "opportunities_count": len(opportunities),
            "pending_count": len(pending),
            "conflicted_count": len(conflicted),
            "has_opportunities": len(opportunities) > 0,
            "results": results,
            "opportunities": opportunities,
        }
