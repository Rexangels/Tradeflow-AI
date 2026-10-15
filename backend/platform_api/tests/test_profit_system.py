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
