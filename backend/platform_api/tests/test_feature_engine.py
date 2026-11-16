from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from platform_api.services.feature_engine import (
    FEATURE_REQUIRED_BARS,
    FEATURE_SET_VERSION,
    build_feature_series,
)


def make_rising_candles(count=220):
    candles = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(count):
        close = 100.0 + (index * 0.2)
        candles.append({
            "time": (start + timedelta(hours=index)).isoformat(),
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000.0 + index,
            "source": "fixture",
        })
    return candles


class FeatureEngineTests(SimpleTestCase):
    def test_feature_engine_is_versioned_and_ready_after_ema200_warmup(self):
        result = build_feature_series(
            make_rising_candles(FEATURE_REQUIRED_BARS),
            symbol="EUR/USD",
            timeframe="1h",
        )

        self.assertEqual(result["featureSetVersion"], FEATURE_SET_VERSION)
        self.assertTrue(result["ready"])
        self.assertIsNone(result["abstainReason"])
        self.assertEqual(result["barCount"], FEATURE_REQUIRED_BARS)
        self.assertEqual(result["latest"]["ema200"], 119.9)
        self.assertEqual(result["latest"]["atr14"], 1.0)
        self.assertAlmostEqual(result["latest"]["rsi14"], 100.0)
        self.assertAlmostEqual(result["latest"]["return1Pct"], (0.2 / 139.6) * 100.0)
        self.assertEqual(result["source"], "fixture")

    def test_insufficient_history_is_an_explicit_abstention(self):
        result = build_feature_series(
            make_rising_candles(80),
            symbol="EURUSD",
            timeframe="1h",
        )

        self.assertFalse(result["ready"])
        self.assertEqual(result["abstainReason"], "insufficient_history")
        self.assertEqual(result["warmupBars"], 120)
        self.assertIsNone(result["latest"]["ema200"])

    def test_each_feature_row_is_causal_and_independent_of_future_bars(self):
        candles = make_rising_candles(240)
        cutoff = 215

        full = build_feature_series(candles, symbol="EURUSD", timeframe="1h")
        truncated = build_feature_series(candles[:cutoff + 1], symbol="EURUSD", timeframe="1h")

        self.assertEqual(
            full["series"][cutoff]["features"],
            truncated["series"][cutoff]["features"],
        )

    def test_optional_spread_cost_is_only_calculated_when_explicitly_supplied(self):
        candles = make_rising_candles(220)
        without_spread = build_feature_series(candles, symbol="EURUSD", timeframe="1h")
        with_spread = build_feature_series(
            candles,
            symbol="EURUSD",
            timeframe="1h",
            spread_pips=1.2,
            pip_size=0.0001,
        )

        self.assertIsNone(without_spread["latest"]["spreadCostPct"])
        expected = ((1.2 * 0.0001) / candles[-1]["close"]) * 100.0
        self.assertAlmostEqual(with_spread["latest"]["spreadCostPct"], expected)

    def test_spread_and_pip_size_must_be_supplied_together(self):
        with self.assertRaisesRegex(ValueError, "supplied together"):
            build_feature_series(
                make_rising_candles(220),
                symbol="EURUSD",
                timeframe="1h",
                spread_pips=1.2,
            )

    def test_feature_engine_does_not_mutate_source_candles(self):
        candles = make_rising_candles(220)
        original = [dict(candle) for candle in candles]

        build_feature_series(candles, symbol="EURUSD", timeframe="1h")

        self.assertEqual(candles, original)
