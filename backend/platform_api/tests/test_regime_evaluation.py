from datetime import datetime, timedelta, timezone
from io import StringIO
import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase

from platform_api.services.regime_evaluation import (
    VALID_REGIMES,
    evaluate_regime_predictions,
)


def reviewed_row(timestamp, actual, predicted, symbol="EURUSD"):
    return {
        "timestamp": timestamp.isoformat(),
        "symbol": symbol,
        "timeframe": "1h",
        "actualRegime": actual,
        "predictedRegime": predicted,
        "classifierVersion": "1.0.0",
        "featureSetVersion": "1.0.0",
        "labelSource": "human_reviewed",
    }


class RegimeEvaluationTests(SimpleTestCase):
    def setUp(self):
        self.start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_metrics_and_confusion_matrix_match_hand_calculation(self):
        records = [
            reviewed_row(self.start, "UPTREND", "UPTREND"),
            reviewed_row(self.start + timedelta(hours=1), "UPTREND", "DOWNTREND"),
            reviewed_row(self.start + timedelta(hours=2), "DOWNTREND", "DOWNTREND"),
            reviewed_row(self.start + timedelta(hours=3), "RANGE", "RANGE"),
            reviewed_row(self.start + timedelta(hours=4), "HIGH_VOLATILITY", "HIGH_VOLATILITY"),
            reviewed_row(self.start + timedelta(hours=5), "UNCERTAIN", "UNCERTAIN"),
        ]

        result = evaluate_regime_predictions(records)

        self.assertEqual(result["sampleCount"], 6)
        self.assertAlmostEqual(result["accuracy"], 5 / 6)
        self.assertAlmostEqual(result["perClass"]["UPTREND"]["precision"], 1.0)
        self.assertAlmostEqual(result["perClass"]["UPTREND"]["recall"], 0.5)
        self.assertAlmostEqual(result["perClass"]["UPTREND"]["f1"], 2 / 3)
        self.assertEqual(result["confusionMatrix"]["UPTREND"]["DOWNTREND"], 1)
        self.assertEqual(result["labelSource"], "human_reviewed")
        self.assertIn("profitability", result["evaluationNote"])

    def test_unreviewed_generated_labels_cannot_be_ground_truth(self):
        record = reviewed_row(self.start, "UPTREND", "UPTREND")
        record["labelSource"] = "model_generated"

        with self.assertRaisesRegex(ValueError, "human_reviewed"):
            evaluate_regime_predictions([record])

    def test_duplicate_symbol_timeframe_timestamp_is_rejected(self):
        record = reviewed_row(self.start, "UPTREND", "UPTREND")

        with self.assertRaisesRegex(ValueError, "Duplicate evaluation row"):
            evaluate_regime_predictions([record, dict(record)])

    def test_naive_timestamps_are_rejected(self):
        record = reviewed_row(datetime(2026, 1, 1), "UPTREND", "UPTREND")

        with self.assertRaisesRegex(ValueError, "timezone"):
            evaluate_regime_predictions([record])

    def test_unknown_label_is_rejected(self):
        record = reviewed_row(self.start, "BUY", "UPTREND")

        with self.assertRaisesRegex(ValueError, "actualRegime"):
            evaluate_regime_predictions([record])

    def test_mixed_classifier_versions_are_rejected(self):
        first = reviewed_row(self.start, "UPTREND", "UPTREND")
        second = reviewed_row(self.start + timedelta(hours=1), "UPTREND", "UPTREND")
        second["classifierVersion"] = "2.0.0"

        with self.assertRaisesRegex(ValueError, "exactly one classifierVersion"):
            evaluate_regime_predictions([first, second])

    def test_management_command_reads_reviewed_csv_and_writes_report(self):
        records = [
            reviewed_row(self.start, "UPTREND", "UPTREND"),
            reviewed_row(self.start + timedelta(hours=1), "RANGE", "RANGE"),
        ]
        fields = [
            "timestamp", "symbol", "timeframe", "actual_regime", "predicted_regime",
            "classifier_version", "feature_set_version", "label_source",
        ]
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "labels.csv"
            output_path = Path(directory) / "report.json"
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for record in records:
                    writer.writerow({
                        "timestamp": record["timestamp"],
                        "symbol": record["symbol"],
                        "timeframe": record["timeframe"],
                        "actual_regime": record["actualRegime"],
                        "predicted_regime": record["predictedRegime"],
                        "classifier_version": record["classifierVersion"],
                        "feature_set_version": record["featureSetVersion"],
                        "label_source": record["labelSource"],
                    })

            call_command(
                "evaluate_market_regimes",
                str(input_path),
                output=str(output_path),
                stdout=StringIO(),
            )
            report = output_path.read_text(encoding="utf-8")

        self.assertIn('"sampleCount": 2', report)
        self.assertIn('"accuracy": 1.0', report)


class RegimeEvaluationContractTests(SimpleTestCase):
    def test_valid_regime_set_is_stable(self):
        self.assertEqual(
            VALID_REGIMES,
            ("UPTREND", "DOWNTREND", "RANGE", "HIGH_VOLATILITY", "UNCERTAIN"),
        )
