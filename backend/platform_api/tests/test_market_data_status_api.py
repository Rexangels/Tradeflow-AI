from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from unittest.mock import patch

from platform_api.views import MarketDataStatusView


class MarketDataStatusDiagnosticsApiTests(SimpleTestCase):
    @patch("platform_api.views.get_candles")
    def test_status_endpoint_exposes_quality_diagnostics(self, get_candles):
        get_candles.return_value = [
            {
                "time": "2026-01-01T10:00:00+00:00",
                "open": 100,
                "high": 105,
                "low": 98,
                "close": 103,
                "volume": 1000,
                "source": "mt5",
            },
            {
                "time": "2026-01-01T11:00:00+00:00",
                "open": 103,
                "high": 107,
                "low": 102,
                "close": 106,
                "volume": 1100,
                "source": "mt5",
            },
        ]
        request = APIRequestFactory().get(
            "/api/v1/market-data/status",
            {"symbol": "EURUSD", "timeframe": "1h"},
        )
        user = User(username="admin", email=settings.DJANGO_ADMIN_EMAIL)
        force_authenticate(request, user=user)

        response = MarketDataStatusView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["source"], "mt5")
        self.assertTrue(response.data["quality"]["valid"])
        self.assertIn("freshness", response.data["quality"])
        self.assertIn("gap_count", response.data["quality"])
