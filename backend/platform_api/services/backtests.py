from __future__ import annotations

from datetime import datetime
from math import sqrt
from uuid import uuid4

from django.utils import timezone

from .indicators import calculate_bollinger_bands, calculate_ema, calculate_rsi
from .model_analysis import analyze_model


TRADING_PERIODS_PER_YEAR = {
    "1m": 525600,
    "5m": 105120,
    "15m": 35040,
    "1h": 8760,
    "4h": 2190,
    "1d": 365,
}
MIN_BACKTEST_CANDLES = 50
MIN_WALK_FORWARD_CANDLES = 120
WALK_FORWARD_TRAIN_FRACTION = 0.5
WALK_FORWARD_TEST_FRACTION = 0.2


def run_backtest(payload: dict, candles: list[dict]) -> dict:
    validated_candles = validate_candles(candles)
    if len(validated_candles) < MIN_BACKTEST_CANDLES:
        raise ValueError("At least 50 candles are required to run a backtest.")

    symbol = payload["symbol"].upper()
    timeframe = payload["timeframe"]
    settings = {
        "startingBalance": payload.get("settings", {}).get("startingBalance", 10000),
        "feeRate": payload.get("settings", {}).get("feeRate", 0.001),
        "slippageRate": payload.get("settings", {}).get("slippageRate", 0.0005),
        "positionSizeFraction": payload.get("settings", {}).get("positionSizeFraction", 0.95),
    }
    agent = payload["agent"].copy()
    agent["id"] = str(agent.get("id") or uuid4())

    result = _simulate_backtest(symbol, timeframe, agent, settings, validated_candles)
    walk_forward = _calculate_walk_forward(symbol, timeframe, agent, settings, validated_candles)
    model_analysis = analyze_model(validated_candles, timeframe, settings)
    warnings = list(walk_forward["warnings"])

    if walk_forward["available"] and walk_forward["averageTestExcessReturnPct"] < 0:
        warnings.append("Walk-forward test windows underperformed buy-and-hold on average.")
    if walk_forward["available"] and walk_forward["benchmarkBeatRatePct"] == 0:
        warnings.append("No out-of-sample walk-forward window beat buy-and-hold.")
    if model_analysis["available"] and model_analysis["performance"]["testAccuracyPct"] < 55:
        warnings.append("Baseline model test accuracy is still weak on the held-out slice.")
    if not model_analysis["available"]:
        warnings.extend(model_analysis["explanation"]["caveats"])

    result["validation"] = {
        "candlesChecked": len(validated_candles),
        "isSorted": True,
        "warnings": warnings,
    }
    result["walkForward"] = walk_forward
    result["modelAnalysis"] = model_analysis
    result["createdAt"] = timezone.now().isoformat()
    return result


def validate_candles(candles: list[dict]) -> list[dict]:
    if not candles:
        raise ValueError("Candle data is required.")

    validated: list[dict] = []
    previous_time: datetime | None = None
    for index, candle in enumerate(candles):
        missing_keys = [key for key in ("time", "open", "high", "low", "close", "volume") if key not in candle]
        if missing_keys:
            raise ValueError(f"Candle at index {index} is missing fields: {', '.join(missing_keys)}.")

        timestamp = trade_timestamp(str(candle["time"]))
        open_price = float(candle["open"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])
        close_price = float(candle["close"])
        volume = float(candle["volume"])

        if min(open_price, high_price, low_price, close_price, volume) < 0:
            raise ValueError(f"Candle at index {index} contains negative values.")
        if high_price < max(open_price, close_price) or low_price > min(open_price, close_price):
            raise ValueError(f"Candle at index {index} has inconsistent OHLC values.")
        if previous_time is not None and timestamp <= previous_time:
            raise ValueError("Candle timestamps must be strictly increasing.")

        validated.append(
            {
                "time": timestamp.isoformat(),
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "volume": volume,
            }
        )
        previous_time = timestamp

    return validated


def trade_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _simulate_backtest(symbol: str, timeframe: str, agent: dict, settings: dict, candles: list[dict]) -> dict:
    close_prices = [entry["close"] for entry in candles]
    ema_fast = calculate_ema(close_prices, 9)
    ema_slow = calculate_ema(close_prices, 21)
    rsi = calculate_rsi(close_prices, 14)
    _, upper_band, lower_band = calculate_bollinger_bands(close_prices, 20, 2)

    cash = settings["startingBalance"]
    quantity_held = 0.0
    entry_price = 0.0
    entry_fee = 0.0
    trades: list[dict] = []
    equity_curve: list[dict] = []
    strategies = [strategy for strategy in agent["strategies"] if strategy["enabled"]]
    bars_in_market = 0

    for index in range(30, len(candles)):
        candle = candles[index]
        buy_signal = _should_buy(index, candles, strategies, ema_fast, ema_slow, rsi, lower_band)
        sell_signal = _should_sell(index, candles, strategies, ema_fast, ema_slow, rsi, upper_band)

        if buy_signal and quantity_held == 0:
            deployable_capital = cash * settings["positionSizeFraction"]
            execution_price = candle["close"] * (1 + settings["slippageRate"])
            quantity = deployable_capital / execution_price
            notional = quantity * execution_price
            fee_paid = notional * settings["feeRate"]

            if quantity > 0 and cash >= notional + fee_paid:
                cash -= notional + fee_paid
                quantity_held = quantity
                entry_price = execution_price
                entry_fee = fee_paid
                trades.append(
                    {
                        "id": str(uuid4()),
                        "type": "buy",
                        "price": _round(execution_price),
                        "time": candle["time"],
                        "quantity": _round(quantity, 8),
                        "notional": _round(notional),
                        "feePaid": _round(fee_paid),
                        "reason": "Strategy entry signal confirmed.",
                    }
                )

        elif sell_signal and quantity_held > 0:
            execution_price = candle["close"] * (1 - settings["slippageRate"])
            notional = quantity_held * execution_price
            fee_paid = notional * settings["feeRate"]
            gross_profit = (execution_price - entry_price) * quantity_held
            net_profit = gross_profit - fee_paid - entry_fee

            cash += notional - fee_paid
            trades.append(
                {
                    "id": str(uuid4()),
                    "type": "sell",
                    "price": _round(execution_price),
                    "time": candle["time"],
                    "quantity": _round(quantity_held, 8),
                    "notional": _round(notional),
                    "feePaid": _round(fee_paid),
                    "profit": _round(net_profit),
                    "reason": "Strategy exit conditions met.",
                }
            )
            quantity_held = 0
            entry_price = 0
            entry_fee = 0

        if quantity_held > 0:
            bars_in_market += 1

        equity_curve.append(
            {
                "time": candle["time"],
                "value": _round(cash + quantity_held * candle["close"]),
            }
        )

    ending_balance = _round(cash + quantity_held * candles[-1]["close"])
    total_profit = _round(ending_balance - settings["startingBalance"])
    total_return_pct = _round((total_profit / settings["startingBalance"]) * 100)
    max_drawdown_pct = _calculate_max_drawdown(equity_curve)
    sell_trades = [trade for trade in trades if trade["type"] == "sell"]
    winning_trades = [trade for trade in sell_trades if trade.get("profit", 0) > 0]
    total_trades = len(sell_trades)
    win_rate = _round((len(winning_trades) / total_trades) * 100) if total_trades else 0
    sharpe_ratio = _calculate_sharpe_ratio(equity_curve, timeframe)
    benchmark = _calculate_buy_and_hold(candles, settings)
    profit_factor = _calculate_profit_factor(sell_trades)
    expectancy = _calculate_expectancy(sell_trades)
    exposure_time_pct = _round((bars_in_market / max(1, len(equity_curve))) * 100)

    return {
        "id": str(uuid4()),
        "symbol": symbol,
        "timeframe": timeframe,
        "agent": agent,
        "settings": settings,
        "metrics": {
            "totalReturnPct": total_return_pct,
            "totalProfit": total_profit,
            "maxDrawdownPct": max_drawdown_pct,
            "sharpeRatio": sharpe_ratio,
            "winRate": win_rate,
            "totalTrades": total_trades,
            "endingBalance": ending_balance,
            "benchmarkReturnPct": benchmark["returnPct"],
            "benchmarkEndingBalance": benchmark["endingBalance"],
            "excessReturnPct": _round(total_return_pct - benchmark["returnPct"]),
            "profitFactor": profit_factor,
            "expectancy": expectancy,
            "exposureTimePct": exposure_time_pct,
        },
        "equityCurve": equity_curve,
        "trades": trades,
    }


def _calculate_walk_forward(symbol: str, timeframe: str, agent: dict, settings: dict, candles: list[dict]) -> dict:
    if len(candles) < MIN_WALK_FORWARD_CANDLES:
        return {
            "available": False,
            "verdict": "insufficient_data",
            "trainCandlesPerWindow": 0,
            "testCandlesPerWindow": 0,
            "windowCount": 0,
            "benchmarkBeatRatePct": 0,
            "profitableWindowPct": 0,
            "averageTestReturnPct": 0,
            "averageTestBenchmarkReturnPct": 0,
            "averageTestExcessReturnPct": 0,
            "averageTestSharpeRatio": 0,
            "averageTestDrawdownPct": 0,
            "warnings": [f"Walk-forward validation needs at least {MIN_WALK_FORWARD_CANDLES} candles."],
            "windows": [],
        }

    train_size = max(MIN_BACKTEST_CANDLES, int(len(candles) * WALK_FORWARD_TRAIN_FRACTION))
    test_size = max(MIN_BACKTEST_CANDLES, int(len(candles) * WALK_FORWARD_TEST_FRACTION))
    max_start = len(candles) - train_size - test_size

    if train_size < MIN_BACKTEST_CANDLES or test_size < MIN_BACKTEST_CANDLES or max_start < 0:
        return {
            "available": False,
            "verdict": "insufficient_data",
            "trainCandlesPerWindow": max(train_size, 0),
            "testCandlesPerWindow": max(test_size, 0),
            "windowCount": 0,
            "benchmarkBeatRatePct": 0,
            "profitableWindowPct": 0,
            "averageTestReturnPct": 0,
            "averageTestBenchmarkReturnPct": 0,
            "averageTestExcessReturnPct": 0,
            "averageTestSharpeRatio": 0,
            "averageTestDrawdownPct": 0,
            "warnings": ["Walk-forward validation could not find a train/test split for this candle window."],
            "windows": [],
        }

    start_indices = _walk_forward_start_indices(len(candles), train_size, test_size)
    windows = []
    for index, start in enumerate(start_indices, start=1):
        train_slice = candles[start : start + train_size]
        test_slice = candles[start + train_size : start + train_size + test_size]
        train_result = _simulate_backtest(symbol, timeframe, agent, settings, train_slice)
        test_result = _simulate_backtest(symbol, timeframe, agent, settings, test_slice)
        test_metrics = test_result["metrics"]
        windows.append(
            {
                "index": index,
                "trainStart": train_slice[0]["time"],
                "trainEnd": train_slice[-1]["time"],
                "testStart": test_slice[0]["time"],
                "testEnd": test_slice[-1]["time"],
                "trainReturnPct": train_result["metrics"]["totalReturnPct"],
                "trainBenchmarkReturnPct": train_result["metrics"]["benchmarkReturnPct"],
                "testReturnPct": test_metrics["totalReturnPct"],
                "testBenchmarkReturnPct": test_metrics["benchmarkReturnPct"],
                "testExcessReturnPct": test_metrics["excessReturnPct"],
                "testSharpeRatio": test_metrics["sharpeRatio"],
                "testMaxDrawdownPct": test_metrics["maxDrawdownPct"],
                "testTotalTrades": test_metrics["totalTrades"],
            }
        )

    benchmark_beats = sum(1 for window in windows if window["testExcessReturnPct"] >= 0)
    profitable_windows = sum(1 for window in windows if window["testReturnPct"] > 0)
    average_test_return = _round(sum(window["testReturnPct"] for window in windows) / len(windows))
    average_test_benchmark = _round(sum(window["testBenchmarkReturnPct"] for window in windows) / len(windows))
    average_test_excess = _round(sum(window["testExcessReturnPct"] for window in windows) / len(windows))
    average_test_sharpe = _round(sum(window["testSharpeRatio"] for window in windows) / len(windows))
    average_test_drawdown = _round(sum(window["testMaxDrawdownPct"] for window in windows) / len(windows))
    benchmark_beat_rate = _round((benchmark_beats / len(windows)) * 100)
    profitable_window_rate = _round((profitable_windows / len(windows)) * 100)

    warnings = []
    if len(windows) < 2:
        warnings.append("Walk-forward validation produced only one out-of-sample window.")

    return {
        "available": True,
        "verdict": _walk_forward_verdict(average_test_excess, benchmark_beat_rate, profitable_window_rate),
        "trainCandlesPerWindow": train_size,
        "testCandlesPerWindow": test_size,
        "windowCount": len(windows),
        "benchmarkBeatRatePct": benchmark_beat_rate,
        "profitableWindowPct": profitable_window_rate,
        "averageTestReturnPct": average_test_return,
        "averageTestBenchmarkReturnPct": average_test_benchmark,
        "averageTestExcessReturnPct": average_test_excess,
        "averageTestSharpeRatio": average_test_sharpe,
        "averageTestDrawdownPct": average_test_drawdown,
        "warnings": warnings,
        "windows": windows,
    }


def _walk_forward_start_indices(total_candles: int, train_size: int, test_size: int) -> list[int]:
    max_start = total_candles - train_size - test_size
    if max_start <= 0:
        return [0]

    starts = [0]
    candidate = test_size
    while candidate <= max_start:
        starts.append(candidate)
        candidate += test_size

    if starts[-1] != max_start:
        starts.append(max_start)
    return sorted(set(starts))


def _walk_forward_verdict(average_test_excess: float, benchmark_beat_rate: float, profitable_window_rate: float) -> str:
    if average_test_excess >= 0 and benchmark_beat_rate >= 60:
        return "pass"
    if average_test_excess >= -5 or profitable_window_rate >= 50:
        return "mixed"
    return "fail"


def _should_buy(index: int, candles: list[dict], strategies: list[dict], ema_fast: list[float], ema_slow: list[float], rsi: list[float], lower_band: list[float]) -> bool:
    for strategy in strategies:
        if strategy["id"] == "trend-following":
            if ema_fast[index] > ema_slow[index] and ema_fast[index - 1] <= ema_slow[index - 1]:
                return True
        if strategy["id"] == "mean-reversion":
            if candles[index]["close"] < lower_band[index] and rsi[index] < 35:
                return True
    return False


def _should_sell(index: int, candles: list[dict], strategies: list[dict], ema_fast: list[float], ema_slow: list[float], rsi: list[float], upper_band: list[float]) -> bool:
    for strategy in strategies:
        if strategy["id"] == "trend-following":
            if ema_fast[index] < ema_slow[index] and ema_fast[index - 1] >= ema_slow[index - 1]:
                return True
        if strategy["id"] == "mean-reversion":
            if candles[index]["close"] > upper_band[index] or rsi[index] > 65:
                return True
    return False


def _calculate_max_drawdown(equity_curve: list[dict]) -> float:
    if not equity_curve:
        return 0
    peak = equity_curve[0]["value"]
    max_drawdown = 0.0
    for point in equity_curve:
        peak = max(peak, point["value"])
        if peak == 0:
            continue
        max_drawdown = max(max_drawdown, ((peak - point["value"]) / peak) * 100)
    return _round(max_drawdown)


def _calculate_sharpe_ratio(equity_curve: list[dict], timeframe: str) -> float:
    if len(equity_curve) < 2:
        return 0

    returns = []
    for index in range(1, len(equity_curve)):
        previous = equity_curve[index - 1]["value"]
        current = equity_curve[index]["value"]
        if previous == 0:
            continue
        returns.append((current - previous) / previous)
    if not returns:
        return 0

    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    standard_deviation = sqrt(variance)
    if standard_deviation == 0:
        return 0

    annualization = sqrt(TRADING_PERIODS_PER_YEAR.get(timeframe, 365))
    return _round((mean / standard_deviation) * annualization)


def _calculate_buy_and_hold(candles: list[dict], settings: dict) -> dict:
    first_close = candles[0]["close"]
    last_close = candles[-1]["close"]
    quantity = settings["startingBalance"] / first_close
    ending_balance = _round(quantity * last_close)
    return_pct = _round(((ending_balance - settings["startingBalance"]) / settings["startingBalance"]) * 100)
    return {"endingBalance": ending_balance, "returnPct": return_pct}


def _calculate_profit_factor(sell_trades: list[dict]) -> float:
    gross_profit = sum(max(trade.get("profit", 0), 0) for trade in sell_trades)
    gross_loss = abs(sum(min(trade.get("profit", 0), 0) for trade in sell_trades))
    if gross_loss == 0:
        return _round(gross_profit) if gross_profit > 0 else 0
    return _round(gross_profit / gross_loss)


def _calculate_expectancy(sell_trades: list[dict]) -> float:
    if not sell_trades:
        return 0
    return _round(sum(trade.get("profit", 0) for trade in sell_trades) / len(sell_trades))


def _round(value: float, precision: int = 4) -> float:
    return round(value, precision)
