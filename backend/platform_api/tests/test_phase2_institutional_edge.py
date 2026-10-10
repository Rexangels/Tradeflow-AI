from django.test import TestCase
from unittest.mock import patch

from platform_api.services.economic_calendar import EconomicCalendarService
from platform_api.services.session_filter import SessionFilterService
from platform_api.services.multi_timeframe import MultiTimeframeService
from platform_api.services.risk_manager import RiskManager


class Phase2InstitutionalEdgeTests(TestCase):
    def test_economic_calendar_events_structure(self):
        events = EconomicCalendarService.get_upcoming_events(hours_ahead=24)
        self.assertIsInstance(events, list)
        self.assertGreater(len(events), 0)
        first = events[0]
        self.assertIn("currency", first)
        self.assertIn("impact", first)
        self.assertIn("minutes_away", first)

    def test_economic_news_shield_blocks_during_window(self):
        # Mock upcoming events to place a HIGH impact USD event 10 minutes away
        mock_events = [
            {
                "id": "USD-test-event",
                "currency": "USD",
                "name": "Fed Interest Rate Decision",
                "impact": "HIGH",
                "scheduled_time": "2026-10-10T14:00:00Z",
                "minutes_away": 10,  # inside 30m buffer
                "forecast": "5.25%",
                "previous": "5.50%",
            }
        ]
        with patch.object(EconomicCalendarService, "get_upcoming_events", return_value=mock_events):
            is_blocked, reason, event = EconomicCalendarService.is_news_blocked("EUR/USD")
            self.assertTrue(is_blocked)
            self.assertIn("ECONOMIC NEWS SHIELD ACTIVE", reason)
            self.assertEqual(event["currency"], "USD")

            # Non-USD pair (e.g. EUR/GBP) should NOT be blocked
            is_blocked_eg, _, _ = EconomicCalendarService.is_news_blocked("EUR/GBP")
            self.assertFalse(is_blocked_eg)

    def test_session_filter_service(self):
        info = SessionFilterService.get_current_session_info()
        self.assertIn("primary_session", info)
        self.assertIn("liquidity_rating", info)
        self.assertIn("liquidity_score", info)
        self.assertIn("favorable_for_trading", info)
        self.assertIn("current_utc_time", info)
        self.assertIsInstance(info["active_sessions"], list)

    def test_multi_timeframe_top_down_confluence(self):
        result = MultiTimeframeService.analyze_top_down("EUR/USD")
        self.assertIn("macro_bias_4h", result)
        self.assertIn(result["macro_bias_4h"], ["BULLISH", "BEARISH", "CONSOLIDATION"])
        self.assertIn("h4", result)
        self.assertIn("h1", result)
        self.assertIn("m15", result)
        self.assertIn("is_aligned", result)
        self.assertIn("confluence_quality", result)
        self.assertIn("composite_score", result)

    def test_risk_manager_integrates_news_shield(self):
        # Mock news shield to be active
        with patch.object(
            EconomicCalendarService,
            "is_news_blocked",
            return_value=(True, "SHIELD TEST ACTIVE", {"name": "Test CPI"}),
        ):
            assessment = RiskManager.assess_order(
                symbol="EUR/USD",
                side="buy",
                qty=1000.0,
                current_price=1.0850,
                stop_loss=1.0800,
                take_profit=1.0950,
            )
            self.assertFalse(assessment["approved"])
            self.assertTrue(assessment.get("news_shield_active"))
            self.assertEqual(assessment["reason"], "SHIELD TEST ACTIVE")
