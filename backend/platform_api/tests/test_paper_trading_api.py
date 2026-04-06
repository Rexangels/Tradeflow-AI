from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from platform_api.auth_utils import ensure_admin_user
from platform_api.models import AppSetting, PaperOrder, PaperPosition, PaperSession
from platform_api.services.paper_trading import get_or_create_account


def detail_text(response) -> str:
    detail = response.data["detail"]
    if isinstance(detail, list):
        return str(detail[0]).lower()
    return str(detail).lower()


@override_settings(
    DJANGO_ADMIN_EMAIL="operator@example.com",
    DJANGO_ADMIN_PASSWORD="super-secret-password",
)
class PaperTradingApiTests(APITestCase):
    def setUp(self):
        self.user = ensure_admin_user()
        self.client = APIClient()
        self.client.force_login(self.user)
        self.account = get_or_create_account(self.user)
        self.session = PaperSession.objects.create(owner=self.user, paper_account=self.account)

    @patch("platform_api.services.paper_trading.latest_price", return_value=100.0)
    def test_account_snapshot_reports_risk_policy(self, _latest_price):
        PaperPosition.objects.create(
            owner=self.user,
            paper_account=self.account,
            symbol="BTCUSDT",
            quantity=0.5,
            average_entry_price=95,
        )
        PaperOrder.objects.create(
            owner=self.user,
            paper_account=self.account,
            session=self.session,
            symbol="BTCUSDT",
            side="sell",
            quantity=0.1,
            fill_price=90,
            notional=9,
            fee_paid=0.01,
            realized_pnl=-125,
            status="filled",
        )

        response = self.client.get("/api/v1/paper-trading/account")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["riskPolicy"]["currentOpenPositions"], 1)
        self.assertEqual(response.data["riskPolicy"]["dailyRealizedLoss"], 125)

    @patch("platform_api.services.paper_trading.latest_price", return_value=100.0)
    def test_rejects_order_that_exceeds_max_order_notional(self, _latest_price):
        response = self.client.post(
            "/api/v1/paper-trading/orders",
            {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 3000,
                "timeframe": "1h",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("max order notional", detail_text(response))

    @patch("platform_api.services.paper_trading.latest_price", return_value=100.0)
    def test_rejects_new_position_when_max_open_positions_reached(self, _latest_price):
        for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            PaperPosition.objects.create(
                owner=self.user,
                paper_account=self.account,
                symbol=symbol,
                quantity=1,
                average_entry_price=100,
            )

        response = self.client.post(
            "/api/v1/paper-trading/orders",
            {
                "symbol": "ADAUSDT",
                "side": "buy",
                "notional": 100,
                "timeframe": "1h",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("max open positions", detail_text(response))

    @patch("platform_api.services.paper_trading.latest_price", return_value=100.0)
    def test_rejects_orders_after_daily_loss_limit_is_hit(self, _latest_price):
        PaperOrder.objects.create(
            owner=self.user,
            paper_account=self.account,
            session=self.session,
            symbol="BTCUSDT",
            side="sell",
            quantity=1,
            fill_price=90,
            notional=90,
            fee_paid=0.1,
            realized_pnl=-600,
            status="filled",
        )

        response = self.client.post(
            "/api/v1/paper-trading/orders",
            {
                "symbol": "ETHUSDT",
                "side": "buy",
                "notional": 100,
                "timeframe": "1h",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("daily realized loss limit", detail_text(response))

    @patch("platform_api.services.paper_trading.latest_price", return_value=100.0)
    def test_respects_kill_switch_from_app_settings(self, _latest_price):
        AppSetting.objects.update_or_create(
            key="paper_risk_policy",
            defaults={
                "value": {
                    "tradingEnabled": False,
                    "maxOrderNotional": 2500,
                    "maxOpenPositions": 3,
                    "maxDailyLoss": 500,
                }
            },
        )

        response = self.client.post(
            "/api/v1/paper-trading/orders",
            {
                "symbol": "BTCUSDT",
                "side": "buy",
                "notional": 100,
                "timeframe": "1h",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("kill switch", detail_text(response))
