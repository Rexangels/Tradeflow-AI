"""Single regime classifier. One function drives scanner, backtester, paper, live.

Regimes:
- trending: trade trend/breakout module only
- ranging: trade mean-reversion module only (or flat if disabled)
- volatility_expansion: flat (stops unreliable, spreads wide)
- news_blocked / rollover: flat (permission veto)

Pure + deterministic: no DB, no network. Callers pass precomputed features
so both live and backtest use identical thresholds.
"""

from __future__ import annotations

from typing import Any

REGIME_VERSION = "1.0.0"

# Thresholds chosen to be conservative and stable across FX majors.
# Tune only on the development slice, never on the locked test slice.
EMA_SLOPE_PIPS_TREND = 1.5      # H4 EMA50 slope over 5 bars, in pips
ADX_TREND_MIN = 18.0            # ADX-proxy: directional separation / ATR
ATR_PCTL_EXPANSION = 0.85       # ATR percentile above this = expansion
ATR_PCTL_COMPRESSION = 0.25     # below this = compressed range


def ema_slope_pips(ema_series: list[float], pip_size: float, lookback: int = 5) -> float:
    if len(ema_series) < lookback + 1 or pip_size <= 0:
        return 0.0
    return (ema_series[-1] - ema_series[-1 - lookback]) / pip_size


def adx_proxy(ema20: float, ema50: float, atr: float) -> float:
    """Directional separation normalized by volatility. 0 = chop, 25+ = trend."""
    if not atr or atr <= 0:
        return 0.0
    return abs(ema20 - ema50) / atr * 10.0


def atr_percentile(atr_series: list[float], window: int = 100) -> float:
    clean = [v for v in atr_series if v == v and v > 0]
    if len(clean) < 10:
        return 0.5
    tail = clean[-window:]
    # Flat ATR (synthetic/test or dead market): no expansion signal.
    if max(tail) - min(tail) < 1e-9:
        return 0.5
    cur = tail[-1]
    below = sum(1 for v in tail if v <= cur)
    return below / len(tail)


def _atr_median(tail: list[float]) -> float:
    s = sorted(tail)
    return s[len(s) // 2] if s else 0.0


def classify_regime(
    ema20: float,
    ema50: float,
    ema200: float,
    price: float,
    atr: float,
    atr_series: list[float],
    ema50_series: list[float],
    pip_size: float,
    news_blocked: bool = False,
    is_rollover: bool = False,
) -> dict[str, Any]:
    """Return {regime, permitted, reasons, features}."""
    reasons: list[str] = []
    features = {
        "slope_pips": round(ema_slope_pips(ema50_series, pip_size), 2),
        "adx_proxy": round(adx_proxy(ema20, ema50, atr), 1),
        "atr_pct": round(atr_percentile(atr_series), 2),
    }

    if news_blocked:
        return {
            "regime": "news_blocked",
            "permitted": "flat",
            "reasons": ["High-impact news buffer: no new trade."],
            "features": features,
            "version": REGIME_VERSION,
        }
    if is_rollover:
        return {
            "regime": "rollover",
            "permitted": "flat",
            "reasons": ["Bank rollover: spreads unreliable."],
            "features": features,
            "version": REGIME_VERSION,
        }
    # Expansion needs BOTH top-decile percentile AND a real lift over median,
    # otherwise flat synthetic/test series false-trigger.
    clean_atr = [v for v in atr_series if v == v and v > 0][-100:]
    median_atr = _atr_median(clean_atr) if clean_atr else 0.0
    if (
        features["atr_pct"] >= ATR_PCTL_EXPANSION
        and median_atr > 0
        and atr >= median_atr * 1.5
    ):
        reasons.append(f"ATR percentile {features['atr_pct']} with lift over median.")
        return {
            "regime": "volatility_expansion",
            "permitted": "flat",
            "reasons": reasons,
            "features": features,
            "version": REGIME_VERSION,
        }

    trending_up = price > ema200 and ema50 >= ema200
    trending_dn = price < ema200 and ema50 <= ema200
    slope_ok = abs(features["slope_pips"]) >= EMA_SLOPE_PIPS_TREND
    adx_ok = features["adx_proxy"] >= ADX_TREND_MIN

    if (trending_up or trending_dn) and (slope_ok or adx_ok):
        reasons.append("EMA stack + slope/ADX agree: trending.")
        return {
            "regime": "trending",
            "permitted": "trend-breakout only",
            "reasons": reasons,
            "features": features,
            "version": REGIME_VERSION,
        }
    reasons.append("No trend evidence: ranging/chop.")
    return {
        "regime": "ranging",
        "permitted": "mean-reversion only or flat",
        "reasons": reasons,
        "features": features,
        "version": REGIME_VERSION,
    }
