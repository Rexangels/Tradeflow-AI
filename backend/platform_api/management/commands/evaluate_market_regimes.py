"""Evaluate classifier outputs against human-reviewed labels.

Usage:
    python manage.py evaluate_market_regimes labels.csv --output report.json
"""
import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from platform_api.services.regime_evaluation import evaluate_regime_predictions


class Command(BaseCommand):
    help = "Build a confusion matrix and metrics from human-reviewed regime labels."

    def add_arguments(self, parser):
        parser.add_argument("dataset", help="CSV file containing reviewed actual/predicted regime labels.")
        parser.add_argument("--output", default="", help="Optional path for the JSON evaluation report.")

    def handle(self, *args, **options):
        dataset_path = Path(options["dataset"]).expanduser()
        required_columns = (
            "timestamp",
            "symbol",
            "timeframe",
            "actual_regime",
            "predicted_regime",
            "classifier_version",
            "feature_set_version",
            "label_source",
        )

        try:
            with dataset_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                missing = [column for column in required_columns if column not in (reader.fieldnames or [])]
                if missing:
                    raise CommandError(
                        "CSV is missing required columns: " + ", ".join(missing)
                    )
                records = [
                    {
                        "timestamp": row["timestamp"],
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                        "actualRegime": row["actual_regime"],
                        "predictedRegime": row["predicted_regime"],
                        "classifierVersion": row["classifier_version"],
                        "featureSetVersion": row["feature_set_version"],
                        "labelSource": row["label_source"],
                    }
                    for row in reader
                ]
            report = evaluate_regime_predictions(records)
        except OSError as exc:
            raise CommandError(f"Could not read evaluation dataset: {exc}") from exc
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        rendered = json.dumps(report, indent=2, sort_keys=True)
        output_path = (options.get("output") or "").strip()
        if output_path:
            try:
                Path(output_path).expanduser().write_text(rendered + "\n", encoding="utf-8")
            except OSError as exc:
                raise CommandError(f"Could not write evaluation report: {exc}") from exc
            self.stdout.write(self.style.SUCCESS(f"Evaluation report written to {output_path}"))
        else:
            self.stdout.write(rendered)
