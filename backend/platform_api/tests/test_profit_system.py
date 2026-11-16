from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase, TestCase
from unittest.mock import patch

from platform_api.services.regime import classify_regime
from platform_api.services.trend_breakout import compute_votes, donchian_break
from platform_api.services.backtests import _monte_carlo_summary, _sensitivity_grid
from platform_api.services.order_execution import OrderExecutionService


def make_candles(count=120, drift=0.0008, start_price=1.0850):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    px = start_price
    for i in range(count):
        px += drift if i % 7 else -drift * 0.5
        out.append({
            "time": (start + timedelta(hours=i)).isoformat(),
            "open": px - 0.0002, "high": px + 0.0004,
            "low": px - 0.0004, "close": px, "volume": 1000,
        })
    return out


class RegimeTests(SimpleTestCase):
    def test_trending_when_stack_and_slope_agree(self):
        ema50 = [1.08 + i * 0.0004 for i in range(12)]
        atrs = [0.0012] * 60
        r = classify_regime(1.095, 1.092, 1.085, 1.096, 0.0015, atrs, ema50, 0.0001)
        self.assertEqual(r["regime"], "trending")

    def test_ranging_without_evidence(self):
        ema50 = [1.085] * 12
        atrs = [0.0012] * 60
        r = classify_regime(1.0851, 1.085, 1.085, 1.0851, 0.0012, atrs, ema50, 0.0001)
        self.assertEqual(r["regime"], "ranging")

    def test_news_and_rollover_veto(self):
        ema50 = [1.08 + i * 0.0004 for i in range(12)]
        atrs = [0.0012] * 60
        self.assertEqual(
            classify_regime(1.096, 1.092, 1.085, 1.096, 0.0015, atrs, ema50, 0.0001, news_blocked=True)["regime"],
            "news_blocked",
        )
        self.assertEqual(
            classify_regime(1.096, 1.092, 1.085, 1.096, 0.0015, atrs, ema50, 0.0001, is_rollover=True)["regime"],
            "rollover",
        )

    def test_expansion_blocks(self):
        ema50 = [1.08 + i * 0.0004 for i in range(12)]
        atrs = [0.001] * 99 + [0.01]
        r = classify_regime(1.096, 1.092, 1.085, 1.096, 0.01, atrs, ema50, 0.0001)
        self.assertEqual(r["regime"], "volatility_expansion")


class VoteTests(SimpleTestCase):
    def test_uptrend_produces_independent_votes(self):
        v = compute_votes(make_candles(160, 0.0009), "EURUSD")
        self.assertIn(v["bias"], ("BULLISH", "BEARISH", "CONSOLIDATION"))
        self.assertIn("trend", v)
        self.assertIn("momentum", v)
        self.assertIn("breakout", v)
        # Mean reversion must never equal a trend vote.
        self.assertTrue(v["mean_reversion"] is None or v["mean_reversion"].endswith("_mr"))

    def test_donchian_detects_break(self):
        base = make_candles(40, 0.0)
        last = dict(base[-1])
        last["close"] = base[-2]["high"] + 0.01
        last["high"] = last["close"] + 0.001
        candles = base[:-1] + [last]
        dc = donchian_break(candles, 20)
        self.assertEqual(dc["break"], "up")


class DiagnosticsTests(SimpleTestCase):
    def test_monte_carlo_needs_trades(self):
        mc = _monte_carlo_summary([10, -5])
        self.assertFalse(mc["available"])

    def test_monte_carlo_profitable_basket(self):
        mc = _monte_carlo_summary([120.0] * 10)
        self.assertTrue(mc["available"])
        self.assertEqual(mc["probProfitable"], 100.0)

    def test_sensitivity_skips_large_windows(self):
        agent = {"strategies": [{"id": "trend-breakout-v1", "enabled": True}]}
        out = _sensitivity_grid("EURUSD", "1h", agent, {}, make_candles(601))
        self.assertFalse(out["available"])


class ScanCommandTests(TestCase):
    def test_flip_writes_signal_once(self):
        from django.core.management import call_command
        from platform_api.models import AISignal

        mtf = {
            "symbol": "EUR/USD", "macro_bias_4h": "BULLISH", "confluence_quality": "EXCELLENT",
            "composite_score": 88.0, "is_aligned": True, "suggested_side": "buy",
            "entry_price": 1.1, "stop_loss": 1.09, "take_profit": 1.12, "rr_ratio": 2.0,
        }
        with patch("platform_api.services.multi_timeframe.MultiTimeframeService.analyze_top_down", return_value=mtf):
            with patch("platform_api.services.economic_calendar.EconomicCalendarService.is_news_blocked", return_value=(False, None, None)):
                with patch("platform_api.services.session_filter.SessionFilterService.get_current_session_info", return_value={"primary_session": "London", "favorable_for_trading": True}):
                    call_command("scan_markets", symbols="EUR/USD")
                    first = AISignal.objects.filter(symbol="EUR/USD").count()
                    call_command("scan_markets", symbols="EUR/USD")
                    second = AISignal.objects.filter(symbol="EUR/USD").count()
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)  # no re-spam without flip


class JournalReviewTests(TestCase):
    def test_review_validates_lesson_and_truncates_note(self):
        from django.contrib.auth.models import User
        from platform_api.models import Agent, TradeLog

        user = User.objects.create_user(username="journalist")
        agent = Agent.objects.create(
            owner=user, name="J", type="custom", reward_style="balanced",
            risk_tolerance=0.4, holding_behavior="swing", strategies=[],
        )
        trade = TradeLog.objects.create(
            agent=agent, symbol="EUR/USD", side="buy", qty=1000.0,
            entry_price=1.1, status="open",
        )
        bad = OrderExecutionService.review_trade(str(trade.id), lesson_tag="made-up")
        self.assertFalse(bad["success"])
        good = OrderExecutionService.review_trade(
            str(trade.id), followed_plan=True, lesson_tag="good-loss", human_note="x" * 200,
        )
        self.assertTrue(good["success"])
        trade.refresh_from_db()
        self.assertTrue(trade.followed_plan)
        self.assertEqual(trade.lesson_tag, "good-loss")
        self.assertEqual(len(trade.human_note), 140)

    def test_journal_snapshot_never_raises(self):
        snap = OrderExecutionService._journal_snapshot("EUR/USD")
        for key in ("regime", "votes", "session", "news_state", "spread_pips"):
            self.assertIn(key, snap)


class ArchitectureUpgradeTests(TestCase):
    def test_score_single_timeframe_triggers_and_no_mr_contamination(self):
        from platform_api.services.trend_breakout import score_single_timeframe

        candles = make_candles(220, drift=0.0009)
        sig = score_single_timeframe(candles, "EURUSD")
        self.assertEqual(sig["direction"], "long")
        self.assertIn("trigger_type", sig)
        self.assertIn(sig["trigger_type"], ("pullback_rejection", "donchian_breakout", "trend_momentum"))

    def test_risk_manager_jpy_unit_risk_and_usd_correlation_guard(self):
        from platform_api.services.risk_manager import RiskManager

        # This test isolates the correlation guard, not the micro-account
        # one-position default. A five-position cap lets the 3rd correlated
        # position be the rule under examination.
        RiskManager.update_rule("max_positions", 5)

        # 1. JPY quote risk conversion: 0.30 JPY on USD/JPY @ 150.00 is $0.002/unit, not $0.30/unit
        jpy_unit_risk = RiskManager.unit_risk_in_usd("USD/JPY", 150.0, 149.70)
        self.assertAlmostEqual(jpy_unit_risk, 0.30 / 150.0, places=5)

        # 2. USD correlation direction mapping
        self.assertEqual(RiskManager.get_usd_direction("EUR/USD", "buy"), "SHORT_USD")
        self.assertEqual(RiskManager.get_usd_direction("GBP/USD", "buy"), "SHORT_USD")
        self.assertEqual(RiskManager.get_usd_direction("USD/JPY", "sell"), "SHORT_USD")
        self.assertEqual(RiskManager.get_usd_direction("USD/JPY", "buy"), "LONG_USD")

        # 3. Block 3rd correlated SHORT_USD position
        open_positions = [
            {"symbol": "EUR/USD", "side": "buy"},
            {"symbol": "GBP/USD", "side": "buy"},
        ]
        with patch("platform_api.services.economic_calendar.EconomicCalendarService.is_news_blocked", return_value=(False, None, None)):
            with patch("platform_api.services.session_filter.SessionFilterService.get_current_session_info", return_value={"is_rollover": False}):
                with patch("platform_api.services.order_execution.OrderExecutionService.get_open_positions", return_value=open_positions):
                    blocked = RiskManager.assess_order(
                        symbol="AUD/USD",
                        side="buy",
                        qty=0.01,
                        current_price=0.6550,
                        stop_loss=0.6520,
                        take_profit=0.6610,
                        account_data={"broker": "mt5", "equity": 100.0, "leverage": 500, "isCentAccount": True},
                    )
                    self.assertFalse(blocked["approved"])
                    self.assertIn("Correlated USD exposure limit", blocked["reason"])

                    # Opposite USD direction (LONG_USD via selling AUD/USD) is allowed
                    allowed = RiskManager.assess_order(
                        symbol="AUD/USD",
                        side="sell",
                        qty=0.01,
                        current_price=0.6550,
                        stop_loss=0.6580,
                        take_profit=0.6490,
                        account_data={"broker": "mt5", "equity": 100.0, "leverage": 500, "isCentAccount": True},
                    )
                    self.assertTrue(allowed["approved"])
                    self.assertEqual(allowed["suggested_qty"], 0.01)

    def test_auto_manage_open_positions_promotes_plus_1r_to_breakeven(self):
        from django.contrib.auth.models import User
        from platform_api.models import Agent, TradeLog
        from platform_api.services.trade_monitor import TradeMonitorService

        user = User.objects.create_user(username="guardian_tester")
        agent = Agent.objects.create(
            owner=user, name="G", type="custom", reward_style="balanced",
            risk_tolerance=0.02, holding_behavior="swing", strategies=[],
        )
        trade = TradeLog.objects.create(
            agent=agent, symbol="EUR/USD", side="buy", qty=1000.0,
            entry_price=1.0850, stop_loss=1.0820, take_profit=1.0910, status="open",
        )
        # Current price is 1.0890 -> +40 pips on a 30-pip SL = +1.33R (> 1.0R trigger)
        mock_positions = [{
            "symbol": "EUR/USD",
            "side": "buy",
            "qty": 0.01,
            "avg_entry_price": 1.0850,
            "current_price": 1.0890,
            "stop_loss": 1.0820,
            "take_profit": 1.0910,
        }]
        mock_protect_res = {
            "success": True,
            "placed_orders": [{"type": "breakeven", "stop_price": 1.0855, "id": "101"}],
        }
        with patch("platform_api.services.order_execution.OrderExecutionService.get_open_positions", return_value=mock_positions):
            with patch.object(TradeMonitorService, "apply_protection", return_value=mock_protect_res) as mock_apply:
                report = TradeMonitorService.auto_manage_open_positions(breakeven_trigger_r=1.0)
                self.assertEqual(len(report["promoted_to_breakeven"]), 1)
                mock_apply.assert_called_once_with("EUR/USD", protect_type="breakeven")
                trade.refresh_from_db()
                self.assertAlmostEqual(trade.stop_loss, 1.0855, places=4)

    def test_triple_barrier_labeling_in_model_samples(self):
        from platform_api.services.model_analysis import _build_samples

        candles = make_candles(120, drift=0.0008)
        samples = _build_samples(candles, horizon=6, settings={"feeRate": 0.001, "slippageRate": 0.0005})
        self.assertGreater(len(samples), 0)
        self.assertIn("tripleBarrierOutcome", samples[0])

