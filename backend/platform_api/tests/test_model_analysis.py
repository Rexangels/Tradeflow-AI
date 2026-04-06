from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from platform_api.services.model_analysis import analyze_model


def make_candles(count: int = 160) -> list[dict]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 100.0
    for index in range(count):
        drift = 0.42 if index % 14 < 9 else -0.28
        noise = 0.06 if index % 5 else -0.03
        price += drift + noise
        candles.append(
            {
                "time": (start + timedelta(hours=index)).isoformat(),
                "open": price - 0.6,
                "high": price + 0.8,
                "low": price - 0.9,
                "close": price,
                "volume": 1000 + ((index % 12) * 25),
            }
        )
    return candles


class ModelAnalysisTests(SimpleTestCase):
    def test_model_analysis_returns_signal_performance_and_explanation(self):
        result = analyze_model(
            make_candles(),
            "1h",
            {
                "startingBalance": 10000,
                "feeRate": 0.001,
                "slippageRate": 0.0005,
                "positionSizeFraction": 0.95,
            },
        )

        self.assertTrue(result["available"])
        self.assertEqual(result["modelType"], "baseline_logistic_regression")
        self.assertGreater(result["trainSamples"], 0)
        self.assertGreater(result["testSamples"], 0)
        self.assertIn(result["signal"]["action"], ("buy", "hold", "sell"))
        self.assertGreaterEqual(result["signal"]["probabilityUpPct"], 0)
        self.assertLessEqual(result["signal"]["probabilityUpPct"], 100)
        self.assertGreater(len(result["topFeatures"]), 0)
        self.assertTrue(result["explanation"]["summary"])
        self.assertGreaterEqual(result["performance"]["testAccuracyPct"], 0)
        self.assertTrue(result["tuning"]["enabled"])
        self.assertGreater(result["tuning"]["candidateCount"], 0)
        self.assertIn("learningRate", result["tuning"]["selectedConfig"])
        self.assertGreater(len(result["tuning"]["topTrials"]), 0)

    def test_model_analysis_returns_unavailable_for_short_series(self):
        result = analyze_model(
            make_candles(70),
            "1h",
            {
                "startingBalance": 10000,
                "feeRate": 0.001,
                "slippageRate": 0.0005,
                "positionSizeFraction": 0.95,
            },
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["signal"]["action"], "hold")
        self.assertGreater(len(result["explanation"]["caveats"]), 0)
        self.assertFalse(result["tuning"]["enabled"])
