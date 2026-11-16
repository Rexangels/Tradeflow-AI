from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from platform_api.auth_utils import ensure_admin_user


@override_settings(
    DJANGO_ADMIN_EMAIL="operator@example.com",
    DJANGO_ADMIN_PASSWORD="super-secret-password",
)
class StrategyCatalogApiTests(APITestCase):
    def setUp(self):
        self.user = ensure_admin_user()
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_catalogue_returns_versioned_research_strategies_without_execution_authority(self):
        response = self.client.get("/api/v1/strategies/catalog")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {item["strategy_id"] for item in response.data},
            {"trend-following", "mean-reversion", "trend-breakout-v1"},
        )
        self.assertTrue(all(item["execution_authority"] == "none" for item in response.data))
        breakout = next(
            item for item in response.data
            if item["strategy_id"] == "trend-breakout-v1"
        )
        self.assertEqual(breakout["version"], "trend-breakout-v1/1.0.0")
        self.assertEqual(breakout["engine"], "trend_breakout_v1")
        self.assertIn("DOWNTREND", breakout["eligible_regimes"])
