from __future__ import annotations

from itertools import product
from math import exp, log, sqrt

from .indicators import calculate_bollinger_bands, calculate_ema, calculate_rsi


HORIZON_BY_TIMEFRAME = {
    "1m": 15,
    "5m": 12,
    "15m": 8,
    "1h": 6,
    "4h": 6,
    "1d": 5,
}
WARMUP_BARS = 21
MIN_MODEL_SAMPLES = 80
MIN_TRAIN_SAMPLES = 30
MIN_VALIDATION_SAMPLES = 10
MIN_TEST_SAMPLES = 10
TRAIN_SPLIT_FRACTION = 0.55
VALIDATION_SPLIT_FRACTION = 0.25
TRAINING_EPOCHS = 220

CANDIDATE_LEARNING_RATES = (0.12, 0.2)
CANDIDATE_REGULARIZATIONS = (0.0005, 0.002)
CANDIDATE_THRESHOLD_PAIRS = ((0.56, 0.44), (0.6, 0.4))

FEATURE_LABELS = {
    "ema_spread": "EMA spread",
    "rsi_centered": "RSI position",
    "band_position": "Bollinger position",
    "momentum_1": "1-bar momentum",
    "momentum_3": "3-bar momentum",
    "volume_ratio": "Volume ratio",
    "volatility_10": "10-bar volatility",
}

FEATURE_DESCRIPTIONS = {
    "ema_spread": ("Fast EMA is above slow EMA, which supports upside continuation.", "Fast EMA is below slow EMA, which leans against upside continuation."),
    "rsi_centered": ("RSI is above neutral, showing positive momentum pressure.", "RSI is below neutral, showing weaker momentum pressure."),
    "band_position": ("Price is pressing the upper half of its Bollinger range.", "Price is leaning toward the lower half of its Bollinger range."),
    "momentum_1": ("The latest bar closed stronger than the prior bar.", "The latest bar closed weaker than the prior bar."),
    "momentum_3": ("Short-term multi-bar momentum is still positive.", "Short-term multi-bar momentum is fading."),
    "volume_ratio": ("Volume is running above its recent average, which can support follow-through.", "Volume is softer than its recent average, which can weaken follow-through."),
    "volatility_10": ("Recent volatility is elevated, which increases uncertainty around the signal.", "Recent volatility is contained, which keeps the signal cleaner."),
}


def analyze_model(candles: list[dict], timeframe: str, settings: dict) -> dict:
    base_horizon = HORIZON_BY_TIMEFRAME.get(timeframe, 6)
    candidate_horizons = sorted({max(3, base_horizon - 2), base_horizon})
    candidate_count = len(candidate_horizons) * len(CANDIDATE_LEARNING_RATES) * len(CANDIDATE_REGULARIZATIONS) * len(CANDIDATE_THRESHOLD_PAIRS)

    best_trial = None
    best_samples: list[dict] | None = None
    best_splits: tuple[list[dict], list[dict], list[dict]] | None = None
    trials = []

    for horizon in candidate_horizons:
        samples = _build_samples(candles, horizon, settings)
        splits = _split_samples(samples, horizon)
        if not splits:
            continue

        train_samples, validation_samples, _test_samples = splits
        train_vectors = [sample["features"] for sample in train_samples]
        validation_vectors = [sample["features"] for sample in validation_samples]
        train_labels = [sample["label"] for sample in train_samples]
        validation_labels = [sample["label"] for sample in validation_samples]
        means, scales = _standardization_stats(train_vectors)
        normalized_train = [_normalize_vector(vector, means, scales) for vector in train_vectors]
        normalized_validation = [_normalize_vector(vector, means, scales) for vector in validation_vectors]

        for learning_rate, regularization, thresholds in product(
            CANDIDATE_LEARNING_RATES,
            CANDIDATE_REGULARIZATIONS,
            CANDIDATE_THRESHOLD_PAIRS,
        ):
            buy_threshold, sell_threshold = thresholds
            coefficients, bias = _fit_logistic_regression(
                normalized_train,
                train_labels,
                learning_rate=learning_rate,
                regularization=regularization,
                epochs=TRAINING_EPOCHS,
            )
            validation_probabilities = [_predict_probability(coefficients, bias, vector) for vector in normalized_validation]
            validation_performance = _performance_summary(validation_probabilities, validation_samples, validation_labels, buy_threshold)
            validation_score = _validation_score(validation_performance)
            trial = {
                "validationScore": _round(validation_score),
                "horizonBars": horizon,
                "learningRate": learning_rate,
                "regularization": regularization,
                "buyThreshold": buy_threshold,
                "sellThreshold": sell_threshold,
                **validation_performance,
            }
            trials.append(trial)
            if best_trial is None or validation_score > best_trial["validationScore"]:
                best_trial = {**trial, "validationScore": validation_score}
                best_samples = samples
                best_splits = splits

    if not best_trial or not best_samples or not best_splits:
        return _unavailable_analysis(candles, base_horizon, candidate_count, "Not enough time-ordered samples to tune and test the baseline model safely.")

    train_samples, validation_samples, test_samples = best_splits
    train_plus_validation = train_samples + validation_samples
    combined_vectors = [sample["features"] for sample in train_plus_validation]
    test_vectors = [sample["features"] for sample in test_samples]
    combined_labels = [sample["label"] for sample in train_plus_validation]
    test_labels = [sample["label"] for sample in test_samples]

    means, scales = _standardization_stats(combined_vectors)
    normalized_combined = [_normalize_vector(vector, means, scales) for vector in combined_vectors]
    normalized_test = [_normalize_vector(vector, means, scales) for vector in test_vectors]
    coefficients, bias = _fit_logistic_regression(
        normalized_combined,
        combined_labels,
        learning_rate=best_trial["learningRate"],
        regularization=best_trial["regularization"],
        epochs=TRAINING_EPOCHS,
    )

    train_probabilities = [_predict_probability(coefficients, bias, vector) for vector in normalized_combined]
    test_probabilities = [_predict_probability(coefficients, bias, vector) for vector in normalized_test]
    latest_sample = best_samples[-1]
    latest_normalized = _normalize_vector(latest_sample["features"], means, scales)
    latest_probability = _predict_probability(coefficients, bias, latest_normalized)
    latest_action = _classify_signal(latest_probability, best_trial["buyThreshold"], best_trial["sellThreshold"])
    top_features = _feature_contributions(latest_sample["features"], latest_normalized, coefficients)
    explanation = _build_explanation(
        latest_sample,
        latest_probability,
        latest_action,
        top_features,
        test_probabilities,
        test_labels,
        best_trial,
    )

    performance = {
        "trainAccuracyPct": _round(_accuracy(train_probabilities, combined_labels) * 100),
        "testAccuracyPct": _round(_accuracy(test_probabilities, test_labels) * 100),
        "testPrecisionPct": _round(_precision(test_probabilities, test_labels) * 100),
        "testRecallPct": _round(_recall(test_probabilities, test_labels) * 100),
        "testAverageForwardReturnPct": _round(_average([sample["futureReturn"] for sample in test_samples]) * 100),
        "predictedLongHitRatePct": _round(_predicted_long_hit_rate(test_probabilities, test_labels, best_trial["buyThreshold"]) * 100),
    }

    tuning = {
        "enabled": True,
        "adaptationMode": "scheduled_retrain",
        "objective": "validation_quality_score",
        "candidateCount": len(trials),
        "trainSamples": len(train_samples),
        "validationSamples": len(validation_samples),
        "testSamples": len(test_samples),
        "selectedConfig": {
            "horizonBars": best_trial["horizonBars"],
            "learningRate": best_trial["learningRate"],
            "regularization": best_trial["regularization"],
            "buyThreshold": best_trial["buyThreshold"],
            "sellThreshold": best_trial["sellThreshold"],
            "epochs": TRAINING_EPOCHS,
        },
        "bestValidationScore": _round(best_trial["validationScore"]),
        "validationPerformance": {
            "accuracyPct": best_trial["accuracyPct"],
            "precisionPct": best_trial["precisionPct"],
            "recallPct": best_trial["recallPct"],
            "predictedLongHitRatePct": best_trial["predictedLongHitRatePct"],
            "predictedLongCount": best_trial["predictedLongCount"],
            "averageForwardReturnPct": best_trial["averageForwardReturnPct"],
        },
        "topTrials": [
            {
                "validationScore": _round(trial["validationScore"]),
                "horizonBars": trial["horizonBars"],
                "learningRate": trial["learningRate"],
                "regularization": trial["regularization"],
                "buyThreshold": trial["buyThreshold"],
                "sellThreshold": trial["sellThreshold"],
                "accuracyPct": trial["accuracyPct"],
                "precisionPct": trial["precisionPct"],
                "recallPct": trial["recallPct"],
                "predictedLongHitRatePct": trial["predictedLongHitRatePct"],
                "predictedLongCount": trial["predictedLongCount"],
                "averageForwardReturnPct": trial["averageForwardReturnPct"],
            }
            for trial in sorted(trials, key=lambda item: item["validationScore"], reverse=True)[:4]
        ],
    }

    return {
        "available": True,
        "modelType": "baseline_logistic_regression",
        "labelHorizonBars": best_trial["horizonBars"],
        "trainSamples": len(train_plus_validation),
        "testSamples": len(test_samples),
        "featuresUsed": [FEATURE_LABELS[name] for name in FEATURE_LABELS],
        "performance": performance,
        "signal": {
            "asOf": latest_sample["time"],
            "action": latest_action,
            "confidencePct": _round(abs(latest_probability - 0.5) * 200),
            "probabilityUpPct": _round(latest_probability * 100),
            "probabilityDownPct": _round((1 - latest_probability) * 100),
        },
        "topFeatures": top_features,
        "explanation": explanation,
        "tuning": tuning,
    }


def _build_samples(candles: list[dict], horizon: int, settings: dict) -> list[dict]:
    closes = [entry["close"] for entry in candles]
    volumes = [entry["volume"] for entry in candles]
    ema_fast = calculate_ema(closes, 9)
    ema_slow = calculate_ema(closes, 21)
    middle_band, upper_band, lower_band = calculate_bollinger_bands(closes, 20, 2)
    rsi = calculate_rsi(closes, 14)
    threshold = max(0.001, (settings.get("feeRate", 0.001) + settings.get("slippageRate", 0.0005)) * 2)

    samples = []
    for index in range(WARMUP_BARS, len(candles) - horizon):
        close_price = closes[index]
        average_volume = _average(volumes[max(0, index - 19) : index + 1]) or volumes[index]
        recent_returns = [
            (closes[offset] / closes[offset - 1]) - 1
            for offset in range(max(1, index - 9), index + 1)
            if closes[offset - 1] != 0
        ]
        band_width = upper_band[index] - lower_band[index]
        band_position = 0.0
        if band_width != 0:
            band_position = (close_price - middle_band[index]) / band_width

        future_close = closes[index + horizon]
        future_return = (future_close / close_price) - 1 if close_price else 0
        label = 1 if future_return > threshold else 0

        samples.append(
            {
                "time": candles[index]["time"],
                "futureReturn": future_return,
                "label": label,
                "features": {
                    "ema_spread": ((ema_fast[index] - ema_slow[index]) / close_price) if close_price else 0,
                    "rsi_centered": (rsi[index] - 50) / 50,
                    "band_position": band_position,
                    "momentum_1": (close_price / closes[index - 1]) - 1 if closes[index - 1] else 0,
                    "momentum_3": (close_price / closes[index - 3]) - 1 if closes[index - 3] else 0,
                    "volume_ratio": (volumes[index] / average_volume) - 1 if average_volume else 0,
                    "volatility_10": _standard_deviation(recent_returns),
                },
            }
        )
    return samples


def _split_samples(samples: list[dict], horizon: int) -> tuple[list[dict], list[dict], list[dict]] | None:
    if len(samples) < MIN_MODEL_SAMPLES:
        return None

    train_boundary = int(len(samples) * TRAIN_SPLIT_FRACTION)
    validation_boundary = int(len(samples) * (TRAIN_SPLIT_FRACTION + VALIDATION_SPLIT_FRACTION))

    train_samples = samples[: max(0, train_boundary - horizon)]
    validation_samples = samples[train_boundary : max(train_boundary, validation_boundary - horizon)]
    test_samples = samples[validation_boundary:]

    if len(train_samples) < MIN_TRAIN_SAMPLES or len(validation_samples) < MIN_VALIDATION_SAMPLES or len(test_samples) < MIN_TEST_SAMPLES:
        return None
    return train_samples, validation_samples, test_samples


def _standardization_stats(vectors: list[dict]) -> tuple[dict, dict]:
    means = {}
    scales = {}
    for name in FEATURE_LABELS:
        values = [vector[name] for vector in vectors]
        means[name] = _average(values)
        scales[name] = _standard_deviation(values) or 1.0
    return means, scales


def _normalize_vector(vector: dict, means: dict, scales: dict) -> dict:
    return {name: (vector[name] - means[name]) / scales[name] for name in FEATURE_LABELS}


def _fit_logistic_regression(vectors: list[dict], labels: list[int], *, learning_rate: float, regularization: float, epochs: int) -> tuple[dict, float]:
    positive_rate = min(max(_average(labels), 0.001), 0.999)
    bias = log(positive_rate / (1 - positive_rate))
    coefficients = {name: 0.0 for name in FEATURE_LABELS}

    for _ in range(epochs):
        gradients = {name: 0.0 for name in FEATURE_LABELS}
        bias_gradient = 0.0
        for vector, label in zip(vectors, labels, strict=False):
            prediction = _predict_probability(coefficients, bias, vector)
            error = prediction - label
            bias_gradient += error
            for name in FEATURE_LABELS:
                gradients[name] += error * vector[name]

        sample_count = max(1, len(vectors))
        bias -= learning_rate * (bias_gradient / sample_count)
        for name in FEATURE_LABELS:
            penalty = regularization * coefficients[name]
            coefficients[name] -= learning_rate * ((gradients[name] / sample_count) + penalty)

    return coefficients, bias


def _predict_probability(coefficients: dict, bias: float, vector: dict) -> float:
    score = bias + sum(coefficients[name] * vector[name] for name in FEATURE_LABELS)
    score = max(min(score, 20), -20)
    return 1 / (1 + exp(-score))


def _performance_summary(probabilities: list[float], samples: list[dict], labels: list[int], buy_threshold: float) -> dict:
    predicted_long_returns = [sample["futureReturn"] for probability, sample in zip(probabilities, samples, strict=False) if probability >= buy_threshold]
    return {
        "accuracyPct": _round(_accuracy(probabilities, labels) * 100),
        "precisionPct": _round(_precision(probabilities, labels) * 100),
        "recallPct": _round(_recall(probabilities, labels) * 100),
        "predictedLongHitRatePct": _round(_predicted_long_hit_rate(probabilities, labels, buy_threshold) * 100),
        "predictedLongCount": len(predicted_long_returns),
        "averageForwardReturnPct": _round(_average(predicted_long_returns) * 100) if predicted_long_returns else 0,
    }


def _validation_score(performance: dict) -> float:
    return (
        performance["accuracyPct"] * 0.35
        + performance["precisionPct"] * 0.3
        + performance["predictedLongHitRatePct"] * 0.25
        + performance["averageForwardReturnPct"] * 10
        - max(0, 4 - performance["predictedLongCount"]) * 1.5
    )


def _classify_signal(probability: float, buy_threshold: float, sell_threshold: float) -> str:
    if probability >= buy_threshold:
        return "buy"
    if probability <= sell_threshold:
        return "sell"
    return "hold"


def _feature_contributions(raw_vector: dict, normalized_vector: dict, coefficients: dict) -> list[dict]:
    contributions = []
    for name in FEATURE_LABELS:
        contribution = normalized_vector[name] * coefficients[name]
        bullish_message, bearish_message = FEATURE_DESCRIPTIONS[name]
        contributions.append(
            {
                "name": name,
                "label": FEATURE_LABELS[name],
                "value": _round(raw_vector[name]),
                "contribution": _round(contribution),
                "effect": "supports_upside" if contribution >= 0 else "leans_downside",
                "detail": bullish_message if contribution >= 0 else bearish_message,
            }
        )
    contributions.sort(key=lambda item: abs(item["contribution"]), reverse=True)
    return contributions[:4]


def _build_explanation(
    latest_sample: dict,
    probability: float,
    action: str,
    top_features: list[dict],
    test_probabilities: list[float],
    test_labels: list[int],
    best_trial: dict,
) -> dict:
    summary = (
        f"The tuned baseline model sees a {probability * 100:.2f}% probability of positive forward returns and currently leans {action.upper()}."
        if action != "hold"
        else f"The tuned baseline model is near the middle at {probability * 100:.2f}% probability of upside, so it prefers HOLD."
    )
    reasoning = [feature["detail"] for feature in top_features]
    caveats = []
    accuracy = _accuracy(test_probabilities, test_labels)
    if accuracy < 0.55:
        caveats.append("Held-out accuracy is still weak, so treat the tuned signal as exploratory rather than production-ready.")
    if _predicted_positive_count(test_probabilities, best_trial["buyThreshold"]) < 5:
        caveats.append("The tuned model produced very few long calls on the held-out slice, so its hit rate is still a small sample.")
    caveats.append(
        f"Hyperparameters were selected on a validation slice with horizon {best_trial['horizonBars']} bars, then checked on a locked test slice before this signal was shown."
    )
    return {
        "summary": summary,
        "reasoning": reasoning,
        "caveats": caveats,
        "asOf": latest_sample["time"],
    }


def _unavailable_analysis(candles: list[dict], horizon: int, candidate_count: int, reason: str) -> dict:
    latest_time = candles[-1]["time"] if candles else ""
    return {
        "available": False,
        "modelType": "baseline_logistic_regression",
        "labelHorizonBars": horizon,
        "trainSamples": 0,
        "testSamples": 0,
        "featuresUsed": [FEATURE_LABELS[name] for name in FEATURE_LABELS],
        "performance": {
            "trainAccuracyPct": 0,
            "testAccuracyPct": 0,
            "testPrecisionPct": 0,
            "testRecallPct": 0,
            "testAverageForwardReturnPct": 0,
            "predictedLongHitRatePct": 0,
        },
        "signal": {
            "asOf": latest_time,
            "action": "hold",
            "confidencePct": 0,
            "probabilityUpPct": 50,
            "probabilityDownPct": 50,
        },
        "topFeatures": [],
        "explanation": {
            "summary": reason,
            "reasoning": [],
            "caveats": [reason],
            "asOf": latest_time,
        },
        "tuning": {
            "enabled": False,
            "adaptationMode": "scheduled_retrain",
            "objective": "validation_quality_score",
            "candidateCount": candidate_count,
            "trainSamples": 0,
            "validationSamples": 0,
            "testSamples": 0,
            "selectedConfig": {
                "horizonBars": horizon,
                "learningRate": 0,
                "regularization": 0,
                "buyThreshold": 0,
                "sellThreshold": 0,
                "epochs": TRAINING_EPOCHS,
            },
            "bestValidationScore": 0,
            "validationPerformance": {
                "accuracyPct": 0,
                "precisionPct": 0,
                "recallPct": 0,
                "predictedLongHitRatePct": 0,
                "predictedLongCount": 0,
                "averageForwardReturnPct": 0,
            },
            "topTrials": [],
        },
    }


def _accuracy(probabilities: list[float], labels: list[int]) -> float:
    if not labels:
        return 0
    correct = 0
    for probability, label in zip(probabilities, labels, strict=False):
        prediction = 1 if probability >= 0.5 else 0
        if prediction == label:
            correct += 1
    return correct / len(labels)


def _precision(probabilities: list[float], labels: list[int]) -> float:
    true_positive = 0
    predicted_positive = 0
    for probability, label in zip(probabilities, labels, strict=False):
        if probability >= 0.5:
            predicted_positive += 1
            if label == 1:
                true_positive += 1
    if predicted_positive == 0:
        return 0
    return true_positive / predicted_positive


def _recall(probabilities: list[float], labels: list[int]) -> float:
    true_positive = 0
    actual_positive = sum(labels)
    if actual_positive == 0:
        return 0
    for probability, label in zip(probabilities, labels, strict=False):
        if probability >= 0.5 and label == 1:
            true_positive += 1
    return true_positive / actual_positive


def _predicted_long_hit_rate(probabilities: list[float], labels: list[int], buy_threshold: float) -> float:
    predicted_positive = 0
    true_positive = 0
    for probability, label in zip(probabilities, labels, strict=False):
        if probability >= buy_threshold:
            predicted_positive += 1
            if label == 1:
                true_positive += 1
    if predicted_positive == 0:
        return 0
    return true_positive / predicted_positive


def _predicted_positive_count(probabilities: list[float], buy_threshold: float) -> int:
    return sum(1 for probability in probabilities if probability >= buy_threshold)


def _average(values: list[float]) -> float:
    if not values:
        return 0
    return sum(values) / len(values)


def _standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0
    mean = _average(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return sqrt(variance)


def _round(value: float, precision: int = 4) -> float:
    return round(value, precision)
