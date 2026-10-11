from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from platform_api.auth_utils import ensure_admin_user


@override_settings(
    DJANGO_ADMIN_EMAIL="operator@example.com",
    DJANGO_ADMIN_PASSWORD="super-secret-password",
)
class MarketDataApiTests(APITestCase):
    def setUp(self):
        self.user = ensure_admin_user()
        self.client = APIClient()
        self.client.force_login(self.user)

    @override_settings(MARKET_DATA_FALLBACK_MODE="strict")
    @patch("platform_api.views.get_candles", side_effect=ValueError("Market data is unavailable right now."))
    def test_market_data_endpoint_returns_validation_error_instead_of_500(self, _mock_get_candles):
        response = self.client.get("/api/v1/market-data/candles?symbol=BTCUSDT&timeframe=1h&limit=120")

        self.assertEqual(response.status_code, 400)
        self.assertIn("market data", str(response.data["detail"]).lower())

    @patch("platform_api.views.latest_price", side_effect=ValueError("Market data is unavailable right now."))
    def test_settings_skips_watchlist_entries_when_prices_fail(self, _mock_latest_price):
        response = self.client.get("/api/v1/settings")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["dashboard"]["watchlist"], [])
        self.assertEqual(response.data["systemStatus"]["marketDataFallbackMode"], "synthetic")

    @patch("platform_api.views.get_candles")
    def test_market_data_status_reports_the_verified_provider(self, mock_get_candles):
        mock_get_candles.return_value = [
            {"time": "2026-10-10T10:00:00+00:00", "source": "mt5"},
            {"time": "2026-10-10T11:00:00+00:00", "source": "mt5"},
        ]

        response = self.client.get("/api/v1/market-data/status?symbol=EUR/USD&timeframe=1h")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])
        self.assertTrue(response.data["isRealData"])
        self.assertEqual(response.data["source"], "mt5")
        self.assertEqual(response.data["latestBarTime"], "2026-10-10T11:00:00+00:00")
