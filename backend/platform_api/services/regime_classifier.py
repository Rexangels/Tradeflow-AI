"""Transparent, causal market-regime labels for feature-engine output.

This module classifies market conditions only. It does not create entries,
position sizing, risk approvals or broker orders.
"""
import math


REGIME_CLASSIFIER_VERSION = "1.0.0"
VOLATILITY_REFERENCE_BARS = 100
VOLATILITY_MIN_REFERENCE_SAMPLES = 50
HIGH_VOLATILITY_PERCENTILE = 90
RANGE_FAST_EMA_ATR_MAX = 0.5
RANGE_SLOW_EMA_ATR_MAX = 1.5
RANGE_RETURN_ATR_MAX = 3.0


def _nearest_rank(values, percentile):
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100.0) * len(ordered)))
    return ordered[rank - 1]


def _is_finite_number(value):
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _trend_bias(features):
    required = (
        "ema20", "ema50", "ema200", "atr14", "atrPct",
        "return12Pct", "closeVsEma200Pct",
    )
    if any(not _is_finite_number(features.get(field)) for field in required):
        return "UNCERTAIN", "Required trend features are still warming up."

    ema20 = float(features["ema20"])
    ema50 = float(features["ema50"])
    ema200 = float(features["ema200"])
    atr = float(features["atr14"])
    atr_pct = float(features["atrPct"])
    return12 = float(features["return12Pct"])
    close_vs_ema200 = float(features["closeVsEma200Pct"])

    if ema20 > ema50 > ema200 and close_vs_ema200 > 0 and return12 > 0:
        return "UPTREND", "EMA20 > EMA50 > EMA200, price is above EMA200, and the 12-bar return is positive."
    if ema20 < ema50 < ema200 and close_vs_ema200 < 0 and return12 < 0:
        return "DOWNTREND", "EMA20 < EMA50 < EMA200, price is below EMA200, and the 12-bar return is negative."

    if atr > 0 and atr_pct > 0:
        fast_separation = abs(ema20 - ema50) / atr
        slow_separation = abs(ema50 - ema200) / atr
        return_magnitude = abs(return12) / atr_pct
        if (
            fast_separation <= RANGE_FAST_EMA_ATR_MAX
            and slow_separation <= RANGE_SLOW_EMA_ATR_MAX
            and return_magnitude <= RANGE_RETURN_ATR_MAX
        ):
            return "RANGE", "EMA separation and 12-bar movement are compressed relative to ATR."

    return "UNCERTAIN", "EMA alignment and movement do not satisfy the trend or range rules."


def classify_regime_series(feature_payload):
    """Classify every bar using only that bar and its preceding feature rows."""
    if not isinstance(feature_payload, dict):
        raise ValueError("A feature-engine payload is required.")
    feature_rows = feature_payload.get("series")
    if not isinstance(feature_rows, list) or not feature_rows:
        raise ValueError("A non-empty feature series is required.")

    required_bars = int(feature_payload.get("requiredBars", 200))
    classifications = []
    for index, row in enumerate(feature_rows):
        if not isinstance(row, dict) or not isinstance(row.get("features"), dict):
            raise ValueError(f"Feature row {index} is invalid.")
        features = row["features"]
        trend_bias, trend_reason = _trend_bias(features)

        required_fields = (
            "ema20", "ema50", "ema200", "atr14", "atrPct",
            "return12Pct", "closeVsEma200Pct", "volatility20Pct",
        )
        is_feature_ready = (
            index + 1 >= required_bars
            and all(_is_finite_number(features.get(field)) for field in required_fields)
        )
        history_start = max(0, index - VOLATILITY_REFERENCE_BARS)
        volatility_history = [
            float(previous["features"]["volatility20Pct"])
            for previous in feature_rows[history_start:index]
            if isinstance(previous, dict)
            and isinstance(previous.get("features"), dict)
            and _is_finite_number(previous["features"].get("volatility20Pct"))
        ]
        current_volatility = features.get("volatility20Pct")
        volatility_threshold = None
        volatility_percentile = None
        high_volatility = False

        if (
            is_feature_ready
            and _is_finite_number(current_volatility)
            and len(volatility_history) >= VOLATILITY_MIN_REFERENCE_SAMPLES
        ):
            volatility_threshold = _nearest_rank(
                volatility_history,
                HIGH_VOLATILITY_PERCENTILE,
            )
            volatility_percentile = (
                sum(value <= float(current_volatility) for value in volatility_history)
                / len(volatility_history)
            ) * 100.0
            high_volatility = float(current_volatility) > volatility_threshold

        if not is_feature_ready:
            regime = "UNCERTAIN"
            reason = "insufficient_feature_history"
        elif len(volatility_history) < VOLATILITY_MIN_REFERENCE_SAMPLES:
            regime = "UNCERTAIN"
            reason = "insufficient_volatility_reference"
        elif high_volatility:
            regime = "HIGH_VOLATILITY"
            reason = (
                "Current 20-bar volatility exceeds the trailing "
                f"{HIGH_VOLATILITY_PERCENTILE}th-percentile reference threshold."
            )
        else:
            regime = trend_bias
            reason = trend_reason

        classifications.append({
            "index": row.get("index", index),
            "time": row.get("time"),
            "regime": regime,
            "trendBias": trend_bias,
            "classificationReady": regime != "UNCERTAIN",
            "reason": reason,
            "volatility20Pct": current_volatility,
            "highVolatilityThreshold": volatility_threshold,
            "volatilityPercentileVsHistory": volatility_percentile,
            "volatilityReferenceSamples": len(volatility_history),
            "liquidityStatus": "not_assessed",
            "executionAuthority": "none",
        })

    latest = classifications[-1]
    return {
        "classifierVersion": REGIME_CLASSIFIER_VERSION,
        "featureSetVersion": feature_payload.get("featureSetVersion"),
        "symbol": feature_payload.get("symbol"),
        "timeframe": feature_payload.get("timeframe"),
        "asOf": latest["time"],
        "barCount": len(feature_rows),
        "ready": latest["classificationReady"],
        "regime": latest["regime"],
        "trendBias": latest["trendBias"],
        "reason": latest["reason"],
        "liquidityStatus": latest["liquidityStatus"],
        "executionAuthority": "none",
        "thresholds": {
            "volatilityReferenceBars": VOLATILITY_REFERENCE_BARS,
            "volatilityMinimumReferenceSamples": VOLATILITY_MIN_REFERENCE_SAMPLES,
            "highVolatilityPercentile": HIGH_VOLATILITY_PERCENTILE,
            "rangeFastEmaAtrMax": RANGE_FAST_EMA_ATR_MAX,
            "rangeSlowEmaAtrMax": RANGE_SLOW_EMA_ATR_MAX,
            "rangeReturnAtrMax": RANGE_RETURN_ATR_MAX,
            "percentileMethod": "nearest_rank",
        },
        "series": classifications,
    }
