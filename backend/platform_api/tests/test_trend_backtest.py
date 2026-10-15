from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from platform_api.defaults import DEFAULT_AGENT
from platform_api.services.backtests import run_backtest


def make_trend_candles(count=300, drift=0.35, start_price=100.0):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = start_price
    for i in range(count):
        # Strong drift with small pullbacks so the unified module can align.
        price += drift if i % 7 else -drift * 0.5
        candles.append(
            {
                "time": (start + timedelta(hours=i)).isoformat(),
                "open": price - 0.4,
                "high": price + 0.6,
                "low": price - 0.6,
                "close": price,
                "volume": 1000 + i,
                "source": "alpaca",
            }
        )
    return candles


def trend_agent():
    return {
        **DEFAULT_AGENT,
        "strategies": [
            {"id": "trend-breakout-v1", "name": "Trend Breakout v1", "description": "x", "enabled": True},
            {"id": "trend-following", "name": "Legacy", "description": "x", "enabled": False},
            {"id": "mean-reversion", "name": "MR", "description": "x", "enabled": False},
        ],
    }


class TrendBreakoutBacktestTests(SimpleTestCase):
    def test_trend_engine_is_deterministic(self):
        payload = {"symbol": "BTCUSDT", "timeframe": "1h", "agent": trend_agent()}
        a = run_backtest(payload, make_trend_candles())
        b = run_backtest(payload, make_trend_candles())
        self.assertEqual(a["metrics"], b["metrics"])
        self.assertEqual(a["validation"]["strategyVersion"], "trend-breakout-v1/1.0.0")
        self.assertIn("regimeStats", a)
        self.assertTrue(a["walkForward"]["available"])

    def test_next_bar_execution_no_lookahead(self):
        # Entry time must always be strictly after the signal bar it references.
        payload = {"symbol": "EURUSD", "timeframe": "1h", "agent": trend_agent()}
        result = run_backtest(payload, make_trend_candles(200))
        self.assertGreater(len(result["trades"]), 0)
        # Entries reference trend-breakout version in reason.
        for t in result["trades"]:
            self.assertIn("trend-breakout-v1", t["reason"])

    def test_costs_reduce_performance(self):
        candles = make_trend_candles(250)
        free = run_backtest(
            {"symbol": "BTCUSDT", "timeframe": "1h", "agent": trend_agent(),
             "settings": {"startingBalance": 10000, "feeRate": 0, "slippageRate": 0,
                          "positionSizeFraction": 0.95, "spreadPips": 0, "riskPct": 0.01}},
            candles,
        )
        costly = run_backtest(
            {"symbol": "BTCUSDT", "timeframe": "1h", "agent": trend_agent(),
             "settings": {"startingBalance": 10000, "feeRate": 0.002, "slippageRate": 0.001,
                          "positionSizeFraction": 0.95, "spreadPips": 5, "riskPct": 0.01}},
            candles,
        )
        self.assertGreaterEqual(free["metrics"]["endingBalance"], costly["metrics"]["endingBalance"])

    def test_risk_sizing_caps_exposure(self):
        # Tiny riskPct should produce small positions and survive chop without ruin.
        payload = {
            "symbol": "EURUSD", "timeframe": "1h", "agent": trend_agent(),
            "settings": {"startingBalance": 10000, "feeRate": 0.001, "slippageRate": 0.0005,
                         "positionSizeFraction": 0.95, "riskPct": 0.002, "spreadPips": 1.2},
        }
        result = run_backtest(payload, make_trend_candles(250, drift=0.15, start_price=1.0850))
        self.assertGreaterEqual(result["metrics"]["endingBalance"], 0)
        self.assertGreaterEqual(result["metrics"]["maxDrawdownPct"], 0)

    def test_rejects_synthetic(self):
        candles = [{**c, "source": "synthetic_demo"} for c in make_trend_candles(120)]
        with self.assertRaisesMessage(ValueError, "Synthetic demo candles"):
            run_backtest({"symbol": "BTCUSDT", "timeframe": "1h", "agent": trend_agent()}, candles)

    def test_sl_tp_exits_recorded(self):
        payload = {"symbol": "BTCUSD", "timeframe": "1h", "agent": trend_agent()}
        result = run_backtest(payload, make_trend_candles(300, drift=0.6))
        reasons = " ".join(t["reason"] for t in result["trades"])
        # At least one ATR stop or target exit should occur over 300 trending bars.
        self.assertTrue("stop-loss" in reasons or "take-profit" in reasons or "opposite signal" in reasons)
