from math import sqrt


def calculate_sma(data: list[float], period: int) -> list[float]:
    output: list[float] = []
    for index, _ in enumerate(data):
        if index < period - 1:
            output.append(float("nan"))
            continue

        window = data[index - period + 1 : index + 1]
        output.append(sum(window) / period)
    return output


def calculate_ema(data: list[float], period: int) -> list[float]:
    output: list[float] = []
    multiplier = 2 / (period + 1)
    for index, price in enumerate(data):
        if index == 0:
            output.append(price)
            continue
        previous = output[index - 1]
        output.append((price - previous) * multiplier + previous)
    return output


def calculate_rsi(data: list[float], period: int = 14) -> list[float]:
    output = [float("nan")] * len(data)
    if len(data) <= period:
        return output

    average_gain = 0.0
    average_loss = 0.0
    for index in range(1, period + 1):
        diff = data[index] - data[index - 1]
        if diff >= 0:
            average_gain += diff
        else:
            average_loss += abs(diff)

    average_gain /= period
    average_loss /= period
    output[period] = _rsi_value(average_gain, average_loss)

    for index in range(period + 1, len(data)):
        diff = data[index] - data[index - 1]
        gain = diff if diff > 0 else 0
        loss = abs(diff) if diff < 0 else 0
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period
        output[index] = _rsi_value(average_gain, average_loss)

    return output


def calculate_bollinger_bands(data: list[float], period: int = 20, multiplier: int = 2) -> tuple[list[float], list[float], list[float]]:
    middle = calculate_sma(data, period)
    upper = [float("nan")] * len(data)
    lower = [float("nan")] * len(data)

    for index in range(period - 1, len(data)):
        average = middle[index]
        window = data[index - period + 1 : index + 1]
        variance = sum((value - average) ** 2 for value in window) / period
        standard_deviation = sqrt(variance)
        upper[index] = average + standard_deviation * multiplier
        lower[index] = average - standard_deviation * multiplier

    return middle, upper, lower


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0:
        return 100
    relative_strength = average_gain / average_loss
    return 100 - 100 / (1 + relative_strength)
