"""Metrics for evaluating regime predictions against human-reviewed labels."""
from datetime import datetime


VALID_REGIMES = (
    "UPTREND",
    "DOWNTREND",
    "RANGE",
    "HIGH_VOLATILITY",
    "UNCERTAIN",
)
REQUIRED_LABEL_SOURCE = "human_reviewed"


def _validate_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Each label requires an ISO-8601 timestamp with timezone.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Each label timestamp must be valid ISO-8601.") from exc
    if parsed.tzinfo is None:
        raise ValueError("Label timestamps must include a timezone.")
    return parsed


def evaluate_regime_predictions(records):
    """Build confusion matrix and metrics from reviewed actual/predicted labels.

    Records are accepted only when labelSource is explicitly human_reviewed.
    A report covers exactly one classifier and feature-set version.
    """
    if not isinstance(records, list) or not records:
        raise ValueError("At least one reviewed label row is required.")

    normalized = []
    seen = set()
    classifier_versions = set()
    feature_versions = set()

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Label row {index} must be an object.")
        if record.get("labelSource") != REQUIRED_LABEL_SOURCE:
            raise ValueError(
                f"Label row {index} is not marked as human_reviewed; generated labels cannot be ground truth."
            )

        actual = str(record.get("actualRegime", "")).strip().upper()
        predicted = str(record.get("predictedRegime", "")).strip().upper()
        if actual not in VALID_REGIMES:
            raise ValueError(f"Label row {index} has an unsupported actualRegime.")
        if predicted not in VALID_REGIMES:
            raise ValueError(f"Label row {index} has an unsupported predictedRegime.")

        symbol = str(record.get("symbol", "")).strip().upper()
        timeframe = str(record.get("timeframe", "")).strip()
        if not symbol or not timeframe:
            raise ValueError(f"Label row {index} requires symbol and timeframe.")

        timestamp = _validate_timestamp(record.get("timestamp"))
        identity = (symbol, timeframe, timestamp.isoformat())
        if identity in seen:
            raise ValueError(
                f"Duplicate evaluation row for {symbol} {timeframe} at {timestamp.isoformat()}."
            )
        seen.add(identity)

        classifier_version = str(record.get("classifierVersion", "")).strip()
        feature_version = str(record.get("featureSetVersion", "")).strip()
        if not classifier_version or not feature_version:
            raise ValueError(f"Label row {index} requires classifierVersion and featureSetVersion.")
        classifier_versions.add(classifier_version)
        feature_versions.add(feature_version)
        normalized.append((actual, predicted))

    if len(classifier_versions) != 1:
        raise ValueError("An evaluation dataset must contain exactly one classifierVersion.")
    if len(feature_versions) != 1:
        raise ValueError("An evaluation dataset must contain exactly one featureSetVersion.")

    confusion = {
        actual: {predicted: 0 for predicted in VALID_REGIMES}
        for actual in VALID_REGIMES
    }
    for actual, predicted in normalized:
        confusion[actual][predicted] += 1

    total = len(normalized)
    correct = sum(confusion[label][label] for label in VALID_REGIMES)
    per_class = {}
    supported_f1 = []
    supported_recall = []

    for label in VALID_REGIMES:
        true_positive = confusion[label][label]
        support = sum(confusion[label].values())
        predicted_count = sum(confusion[actual][label] for actual in VALID_REGIMES)
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / support if support else None
        f1 = (
            (2.0 * precision * recall) / (precision + recall)
            if recall is not None and precision + recall > 0
            else (0.0 if recall is not None else None)
        )
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
            "predictedCount": predicted_count,
        }
        if support:
            supported_f1.append(f1)
            supported_recall.append(recall)

    return {
        "classifierVersion": next(iter(classifier_versions)),
        "featureSetVersion": next(iter(feature_versions)),
        "labelSource": REQUIRED_LABEL_SOURCE,
        "sampleCount": total,
        "accuracy": correct / total,
        "macroF1": sum(supported_f1) / len(supported_f1) if supported_f1 else None,
        "balancedAccuracy": sum(supported_recall) / len(supported_recall) if supported_recall else None,
        "classOrder": list(VALID_REGIMES),
        "confusionMatrix": confusion,
        "perClass": per_class,
        "evaluationNote": (
            "Metrics are descriptive for this reviewed sample only. "
            "They do not establish profitability or out-of-sample generalization."
        ),
    }
