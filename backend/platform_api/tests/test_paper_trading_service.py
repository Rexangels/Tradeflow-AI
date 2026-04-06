from unittest.mock import patch

from django.test import TestCase, override_settings

from platform_api.auth_utils import ensure_admin_user
from platform_api.services.paper_trading import get_or_create_account, place_order


@override_settings(
    DJANGO_ADMIN_EMAIL="operator@example.com",
    DJANGO_ADMIN_PASSWORD="super-secret-password",
)
class PaperTradingServiceTests(TestCase):
    def setUp(self):
        self.user = ensure_admin_user()
        self.account = get_or_create_account(self.user)

    @patch("platform_api.services.paper_trading.latest_price", return_value=100.0)
    def test_buy_then_sell_updates_account_and_removes_position(self, _latest_price):
        buy_result = place_order(
            self.user,
            {
                "symbol": "ETHUSDT",
                "side": "buy",
                "notional": 250,
                "timeframe": "1h",
            },
        )

        self.account.refresh_from_db()
        self.assertEqual(len(buy_result["account"]["positions"]), 1)
        self.assertLess(self.account.cash_balance, 10000)
        self.assertEqual(self.account.realized_pnl, 0)

        sell_result = place_order(
            self.user,
            {
                "symbol": "ETHUSDT",
                "side": "sell",
                "quantity": buy_result["order"]["quantity"],
                "timeframe": "1h",
            },
        )

        self.account.refresh_from_db()
        self.assertEqual(sell_result["account"]["positions"], [])
        self.assertAlmostEqual(self.account.realized_pnl, sell_result["order"]["realizedPnl"], places=4)
        self.assertGreater(sell_result["account"]["cashBalance"], buy_result["account"]["cashBalance"])

    @patch("platform_api.services.paper_trading.latest_price", side_effect=[100.0, 100.0, 120.0, 120.0])
    def test_multiple_buys_update_average_entry_price(self, _latest_price):
        first = place_order(
            self.user,
            {
                "symbol": "SOLUSDT",
                "side": "buy",
                "notional": 200,
                "timeframe": "1h",
            },
        )
        second = place_order(
            self.user,
            {
                "symbol": "SOLUSDT",
                "side": "buy",
                "notional": 240,
                "timeframe": "1h",
            },
        )

        position = second["account"]["positions"][0]
        self.assertEqual(first["account"]["riskPolicy"]["currentOpenPositions"], 1)
        self.assertEqual(second["account"]["riskPolicy"]["currentOpenPositions"], 1)
        self.assertGreater(position["quantity"], first["account"]["positions"][0]["quantity"])
        self.assertGreater(position["averageEntryPrice"], first["account"]["positions"][0]["averageEntryPrice"])
