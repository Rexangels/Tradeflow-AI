from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from platform_api.defaults import DEFAULT_AGENT
from platform_api.services.backtests import run_backtest


def make_candles(count: int = 120) -> list[dict]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 100.0
    for index in range(count):
        price += 0.35 if index % 6 else -0.1
        candles.append(
            {
                "time": (start + timedelta(hours=index)).isoformat(),
                "open": price - 0.5,
                "high": price + 0.75,
                "low": price - 0.9,
                "close": price,
                "volume": 1000 + index,
            }
        )
    return candles


class BacktestEngineTests(SimpleTestCase):
    def test_backtest_returns_deterministic_metrics_and_validation(self):
        payload = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "agent": DEFAULT_AGENT,
            "settings": {
                "startingBalance": 10000,
                "feeRate": 0.001,
                "slippageRate": 0.0005,
                "positionSizeFraction": 0.95,
            },
        }

        first = run_backtest(payload, make_candles())
        second = run_backtest(payload, make_candles())

        self.assertEqual(first["symbol"], "BTCUSDT")
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertEqual(first["validation"], second["validation"])
        self.assertEqual(first["validation"]["candlesChecked"], 120)
        self.assertTrue(first["validation"]["isSorted"])
        self.assertIn("benchmarkReturnPct", first["metrics"])
        self.assertIn("benchmarkEndingBalance", first["metrics"])
        self.assertIn("excessReturnPct", first["metrics"])
        self.assertIn("profitFactor", first["metrics"])
        self.assertIn("expectancy", first["metrics"])
        self.assertIn("exposureTimePct", first["metrics"])
        self.assertIn("walkForward", first)
        self.assertTrue(first["walkForward"]["available"])
        self.assertGreaterEqual(first["walkForward"]["windowCount"], 1)
        self.assertIn("benchmarkBeatRatePct", first["walkForward"])
        self.assertIn("verdict", first["walkForward"])
        self.assertIn("modelAnalysis", first)
        self.assertTrue(first["modelAnalysis"]["available"])
        self.assertIn("signal", first["modelAnalysis"])
        self.assertIn("performance", first["modelAnalysis"])
        self.assertIn("tuning", first["modelAnalysis"])
        self.assertTrue(first["modelAnalysis"]["tuning"]["enabled"])
        self.assertGreaterEqual(first["modelAnalysis"]["signal"]["probabilityUpPct"], 0)
        self.assertLessEqual(first["modelAnalysis"]["signal"]["probabilityUpPct"], 100)
        self.assertGreaterEqual(first["metrics"]["endingBalance"], 0)

    def test_backtest_rejects_unsorted_candles(self):
        candles = make_candles()
        candles[20], candles[21] = candles[21], candles[20]

        payload = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "agent": DEFAULT_AGENT,
        }

        with self.assertRaisesMessage(ValueError, "strictly increasing"):
            run_backtest(payload, candles)

    def test_backtest_rejects_inconsistent_ohlc_data(self):
        candles = make_candles()
        candles[10]["high"] = candles[10]["close"] - 1

        payload = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "agent": DEFAULT_AGENT,
        }

        with self.assertRaisesMessage(ValueError, "inconsistent OHLC"):
            run_backtest(payload, candles)

    def test_backtest_with_no_enabled_strategies_takes_no_trades(self):
        payload = {
            "symbol": "ETHUSDT",
            "timeframe": "1h",
            "agent": {
                **DEFAULT_AGENT,
                "strategies": [{**strategy, "enabled": False} for strategy in DEFAULT_AGENT["strategies"]],
            },
            "settings": {
                "startingBalance": 10000,
                "feeRate": 0.001,
                "slippageRate": 0.0005,
                "positionSizeFraction": 0.95,
            },
        }

        result = run_backtest(payload, make_candles())

        self.assertEqual(result["trades"], [])
        self.assertEqual(result["metrics"]["totalTrades"], 0)
        self.assertEqual(result["metrics"]["endingBalance"], 10000.0)
        self.assertEqual(result["metrics"]["exposureTimePct"], 0)

    def test_walk_forward_windows_include_train_and_test_ranges(self):
        payload = {
            "symbol": "ETHUSDT",
            "timeframe": "1h",
            "agent": DEFAULT_AGENT,
            "settings": {
                "startingBalance": 10000,
                "feeRate": 0.001,
                "slippageRate": 0.0005,
                "positionSizeFraction": 0.95,
            },
        }

        result = run_backtest(payload, make_candles())
        window = result["walkForward"]["windows"][0]

        self.assertIn("trainStart", window)
        self.assertIn("testStart", window)
        self.assertIn("testExcessReturnPct", window)
        self.assertGreaterEqual(result["walkForward"]["benchmarkBeatRatePct"], 0)
        self.assertLessEqual(result["walkForward"]["benchmarkBeatRatePct"], 100)

    @patch("platform_api.services.backtests._should_sell")
    @patch("platform_api.services.backtests._should_buy")
    def test_engine_never_duplicates_position_entries_for_signal_sequence(self, mock_should_buy, mock_should_sell):
        payload = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "agent": DEFAULT_AGENT,
            "settings": {
                "startingBalance": 10000,
                "feeRate": 0.001,
                "slippageRate": 0.0005,
                "positionSizeFraction": 0.95,
            },
        }

        buy_indices = {35, 55}
        sell_indices = {45, 65}
        mock_should_buy.side_effect = lambda index, *_args: index in buy_indices
        mock_should_sell.side_effect = lambda index, *_args: index in sell_indices

        result = run_backtest(payload, make_candles())
        trade_types = [trade["type"] for trade in result["trades"]]

        self.assertEqual(trade_types, ["buy", "sell", "buy", "sell"])

    def test_fees_and_slippage_reduce_performance_relative_to_zero_costs(self):
        base_payload = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "agent": DEFAULT_AGENT,
        }
        candles = make_candles()

        free_result = run_backtest(
            {
                **base_payload,
                "settings": {
                    "startingBalance": 10000,
                    "feeRate": 0,
                    "slippageRate": 0,
                    "positionSizeFraction": 0.95,
                },
            },
            candles,
        )
        cost_result = run_backtest(
            {
                **base_payload,
                "settings": {
                    "startingBalance": 10000,
                    "feeRate": 0.001,
                    "slippageRate": 0.0005,
                    "positionSizeFraction": 0.95,
                },
            },
            candles,
        )

        self.assertGreaterEqual(free_result["metrics"]["endingBalance"], cost_result["metrics"]["endingBalance"])
        self.assertGreaterEqual(free_result["metrics"]["totalProfit"], cost_result["metrics"]["totalProfit"])
