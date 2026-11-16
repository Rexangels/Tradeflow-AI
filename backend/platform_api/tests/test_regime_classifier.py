from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from platform_api.services.feature_engine import build_feature_series
from platform_api.services.regime_classifier import (
    REGIME_CLASSIFIER_VERSION,
    classify_regime_series,
)


def make_candles(count=220, direction="up"):
    candles = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(count):
        if direction == "up":
            close = 100.0 + index * 0.2
            open_price = close - 0.1
        elif direction == "down":
            close = 140.0 - index * 0.2
            open_price = close + 0.1
        else:
            close = 100.0
            open_price = close
        candles.append({
            "time": (start + timedelta(hours=index)).isoformat(),
            "open": open_price,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000.0 + index if direction != "flat" else 1000.0,
            "source": "fixture",
        })
    return candles


def build_trend_payload(count=220):
    return build_feature_series(
        make_candles(count, "up"),
        symbol="EURUSD",
        timeframe="1h",
    )


class RegimeClassifierTests(SimpleTestCase):
    def test_rising_market_is_labeled_uptrend_without_execution_authority(self):
        features = build_trend_payload()
        result = classify_regime_series(features)

        self.assertEqual(result["classifierVersion"], REGIME_CLASSIFIER_VERSION)
        self.assertTrue(result["ready"])
        self.assertEqual(result["regime"], "UPTREND")
        self.assertEqual(result["trendBias"], "UPTREND")
        self.assertEqual(result["executionAuthority"], "none")
        self.assertEqual(result["liquidityStatus"], "not_assessed")

    def test_falling_market_is_labeled_downtrend(self):
        features = build_feature_series(
            make_candles(220, "down"),
            symbol="EURUSD",
            timeframe="1h",
        )
        result = classify_regime_series(features)

        self.assertEqual(result["regime"], "DOWNTREND")
        self.assertEqual(result["trendBias"], "DOWNTREND")

    def test_compressed_market_is_labeled_range(self):
        features = build_feature_series(
            make_candles(220, "flat"),
            symbol="EURUSD",
            timeframe="1h",
        )
        result = classify_regime_series(features)

        self.assertEqual(result["regime"], "RANGE")
        self.assertEqual(result["trendBias"], "RANGE")

    def test_high_volatility_uses_only_preceding_reference_bars(self):
        payload = build_trend_payload(220)
        for row in payload["series"]:
            row["features"]["volatility20Pct"] = 0.1
        payload["series"][-1]["features"]["volatility20Pct"] = 0.5
        payload["latest"]["volatility20Pct"] = 0.5

        result = classify_regime_series(payload)

        self.assertEqual(result["regime"], "HIGH_VOLATILITY")
        self.assertEqual(result["trendBias"], "UPTREND")
        self.assertAlmostEqual(result["latest"]["highVolatilityThreshold"], 0.1)
        self.assertEqual(result["latest"]["volatilityReferenceSamples"], 100)

    def test_uncertain_is_returned_when_feature_history_is_short(self):
        features = build_trend_payload(100)
        result = classify_regime_series(features)

        self.assertFalse(result["ready"])
        self.assertEqual(result["regime"], "UNCERTAIN")
        self.assertEqual(result["reason"], "insufficient_feature_history")
        self.assertEqual(result["executionAuthority"], "none")

    def test_regime_at_a_timestamp_is_unchanged_by_future_bars(self):
        candles = make_candles(240, "up")
        cutoff = 215
        full_features = build_feature_series(candles, symbol="EURUSD", timeframe="1h")
        prefix_features = build_feature_series(candles[:cutoff + 1], symbol="EURUSD", timeframe="1h")

        full_result = classify_regime_series(full_features)
        prefix_result = classify_regime_series(prefix_features)

        self.assertEqual(
            full_result["series"][cutoff],
            prefix_result["series"][cutoff],
        )

    def test_liquidity_is_not_inferred_from_raw_volume(self):
        result = classify_regime_series(build_trend_payload())

        self.assertEqual(result["liquidityStatus"], "not_assessed")
        self.assertEqual(result["executionAuthority"], "none")
