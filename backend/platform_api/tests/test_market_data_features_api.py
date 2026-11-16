from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from platform_api.auth_utils import ensure_admin_user


def make_feature_candles(count=220):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index in range(count):
        close = 100.0 + (index * 0.2)
        candles.append({
            "time": (start + timedelta(hours=index)).isoformat(),
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000.0 + index,
            "source": "fixture",
        })
    return candles


@override_settings(
    DJANGO_ADMIN_EMAIL="operator@example.com",
    DJANGO_ADMIN_PASSWORD="super-secret-password",
)
class MarketDataFeaturesApiTests(APITestCase):
    def setUp(self):
        self.user = ensure_admin_user()
        self.client = APIClient()
        self.client.force_login(self.user)

    @patch("platform_api.views.get_candles", return_value=make_feature_candles())
    def test_features_endpoint_returns_versioned_causal_feature_series(self, mock_get_candles):
        response = self.client.get(
            "/api/v1/market-data/features?symbol=EUR/USD&timeframe=1h&limit=220"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["featureSetVersion"], "1.0.0")
        self.assertIn("causality", response.data["featureDefinitions"])
        self.assertTrue(response.data["ready"])
        self.assertEqual(response.data["symbol"], "EURUSD")
        self.assertEqual(response.data["source"], "fixture")
        self.assertEqual(response.data["barCount"], 220)
        self.assertEqual(len(response.data["series"]), 220)
        self.assertAlmostEqual(response.data["latest"]["rsi14"], 100.0)
        self.assertEqual(response.data["regime"]["regime"], "UPTREND")
        self.assertEqual(response.data["regime"]["executionAuthority"], "none")
        self.assertEqual(response.data["regime"]["liquidityStatus"], "not_assessed")
        mock_get_candles.assert_called_once_with(
            "EUR/USD",
            "1h",
            limit=220,
            force_refresh=False,
        )

    @patch("platform_api.views.get_candles", return_value=make_feature_candles(80))
    def test_features_endpoint_returns_no_trade_readiness_for_short_history(self, _mock_get_candles):
        response = self.client.get(
            "/api/v1/market-data/features?symbol=EUR/USD&timeframe=1h&limit=80"
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["ready"])
        self.assertEqual(response.data["abstainReason"], "insufficient_history")
        self.assertEqual(response.data["warmupBars"], 120)

    def test_features_endpoint_rejects_spread_without_pip_size(self):
        response = self.client.get(
            "/api/v1/market-data/features?symbol=EUR/USD&timeframe=1h&limit=220&spreadPips=1.2"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("spreadPips and pipSize", str(response.data))
