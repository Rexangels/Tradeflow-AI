from datetime import datetime, timedelta, timezone

from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from platform_api.auth_utils import ensure_admin_user
from platform_api.defaults import DEFAULT_AGENT


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


@override_settings(
    DJANGO_ADMIN_EMAIL="operator@example.com",
    DJANGO_ADMIN_PASSWORD="super-secret-password",
)
class BacktestApiTests(APITestCase):
    def setUp(self):
        self.user = ensure_admin_user()
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_backtest_api_persists_validation_payload(self):
        response = self.client.post(
            "/api/v1/backtests",
            {
                "symbol": "BTCUSDT",
                "timeframe": "1h",
                "candles": make_candles(),
                "agent": DEFAULT_AGENT,
                "settings": {
                    "startingBalance": 10000,
                    "feeRate": 0.001,
                    "slippageRate": 0.0005,
                    "positionSizeFraction": 0.95,
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["validation"]["candlesChecked"], 120)
        self.assertTrue(response.data["validation"]["isSorted"])
        self.assertEqual(response.data["agent"]["name"], DEFAULT_AGENT["name"])
        self.assertTrue(response.data["walkForward"]["available"])
        self.assertGreaterEqual(response.data["walkForward"]["windowCount"], 1)
        self.assertTrue(response.data["modelAnalysis"]["available"])
        self.assertIn("summary", response.data["modelAnalysis"]["explanation"])
        self.assertTrue(response.data["modelAnalysis"]["tuning"]["enabled"])

        list_response = self.client.get("/api/v1/backtests")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data[0]["validation"]["candlesChecked"], 120)
        self.assertIn("benchmarkReturnPct", list_response.data[0]["metrics"])
        self.assertIn("walkForward", list_response.data[0])
        self.assertIn("modelAnalysis", list_response.data[0])
