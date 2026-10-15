from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from platform_api.services.economic_calendar import EconomicCalendarService


def _sample_feed():
    now = timezone.now().astimezone(dt_timezone.utc)
    return [
        {"title": "CPI m/m", "country": "USD",
         "date": (now + timedelta(hours=2)).isoformat(),
         "impact": "High", "forecast": "0.6%", "previous": "0.4%"},
        {"title": "ECB President Lagarde Speaks", "country": "EUR",
         "date": (now + timedelta(hours=3)).isoformat(),
         "impact": "Medium", "forecast": "", "previous": ""},
        {"title": "Bank Holiday", "country": "JPY",
         "date": (now + timedelta(hours=4)).isoformat(),
         "impact": "Holiday", "forecast": "", "previous": ""},
    ]


def fake_response(payload):
    import json

    m = MagicMock()
    m.read.return_value = json.dumps(payload).encode("utf-8")
    m.__enter__.return_value = m
    m.__exit__.return_value = False
    return m


class CalendarLiveTests(SimpleTestCase):
    def setUp(self):
        EconomicCalendarService._CACHE = {"events_raw": [], "fetched_at": None, "source": "uninitialized"}

    def test_live_feed_parses_high_impact(self):
        with patch("urllib.request.urlopen", return_value=fake_response(_sample_feed())):
            events = EconomicCalendarService.get_upcoming_events(hours_ahead=24 * 30)
        usd_high = [e for e in events if e["currency"] == "USD" and e["impact"] == "HIGH"]
        self.assertGreaterEqual(len(usd_high), 1)
        self.assertEqual(usd_high[0]["source"], "live_ff_mirror")
        self.assertIn("minutes_away", usd_high[0])
        status = EconomicCalendarService.get_calendar_status()
        self.assertTrue(status["is_live"])

    def test_shield_blocks_on_live_high_impact(self):
        # Place a HIGH USD event 10 minutes in the future relative to now.
        now = timezone.now().astimezone(dt_timezone.utc)
        live_raw = [{
            "title": "CPI y/y", "country": "USD",
            "date": (now + timedelta(minutes=10)).isoformat(),
            "impact": "High", "forecast": "3.6%", "previous": "3.4%",
        }]
        with patch("urllib.request.urlopen", return_value=fake_response(live_raw)):
            blocked, reason, ev = EconomicCalendarService.is_news_blocked("EUR/USD")
        self.assertTrue(blocked)
        self.assertIn("ECONOMIC NEWS SHIELD ACTIVE", reason)
        self.assertEqual(ev["currency"], "USD")

    def test_fallback_when_provider_down(self):
        with patch("urllib.request.urlopen", side_effect=Exception("offline")):
            events = EconomicCalendarService.get_upcoming_events(hours_ahead=24)
        self.assertGreater(len(events), 0)
        self.assertTrue(all(e["source"] == "simulated_fallback" for e in events))
        status = EconomicCalendarService.get_calendar_status()
        self.assertFalse(status["is_live"])

    def test_medium_events_do_not_block(self):
        now = timezone.now().astimezone(dt_timezone.utc)
        live_raw = [{
            "title": "ECB President Lagarde Speaks", "country": "EUR",
            "date": (now + timedelta(minutes=5)).isoformat(),
            "impact": "Medium", "forecast": "", "previous": "",
        }]
        with patch("urllib.request.urlopen", return_value=fake_response(live_raw)):
            blocked, _, _ = EconomicCalendarService.is_news_blocked("EUR/USD")
        # EUR medium event: need HIGH to block. EUR/USD contains EUR but impact is MEDIUM.
        # USD side has no event, so no block.
        self.assertFalse(blocked)
