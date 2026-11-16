from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from platform_api.services.mt5_client import MT5Client
from platform_api.services.order_execution import OrderExecutionService


class Phase3MT5AdapterTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="admin@tradeflow.local",
            email="admin@tradeflow.local",
            password="password123",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_mt5_client_initialization_does_not_invent_account_state(self):
        client = MT5Client(login=477536967, server="Exness-MT5Trial9")
        self.assertEqual(client.login, 477536967)
        self.assertEqual(client.server, "Exness-MT5Trial9")

        overview = client.get_account_overview()
        self.assertEqual(overview["broker"], "mt5")
        self.assertEqual(overview["mode"], "disconnected")
        self.assertIsNone(overview["accountNumber"])
        self.assertIsNone(overview["currency"])
        self.assertFalse(overview["isCentAccount"])
        self.assertEqual(overview["balance"], 0.0)
        self.assertEqual(overview["equity"], 0.0)
        self.assertFalse(overview["connected"])

    def test_broker_switching_preserves_disconnected_mt5_state(self):
        active = OrderExecutionService.set_active_broker("mt5")
        self.assertEqual(active, "mt5")
        self.assertEqual(OrderExecutionService.get_active_broker(), "mt5")

        overview = OrderExecutionService.get_account_overview()
        self.assertEqual(overview["broker"], "mt5")
        self.assertEqual(overview["mode"], "disconnected")
        self.assertIsNone(overview["accountNumber"])
        self.assertFalse(overview["connected"])

        active_alpaca = OrderExecutionService.set_active_broker("alpaca")
        self.assertEqual(active_alpaca, "alpaca")
        self.assertEqual(OrderExecutionService.get_active_broker(), "alpaca")

    @patch("platform_api.services.mt5_client.get_mt5_client")
    @patch("platform_api.forex_views.get_alpaca_client")
    def test_active_broker_api_endpoint(self, mock_get_alpaca_client, mock_get_mt5_client):
        alpaca_client = mock_get_alpaca_client.return_value
        alpaca_client.mode = "paper"
        alpaca_client.get_account.return_value = {
            "equity": "25000.00",
            "status": "ACTIVE",
        }
        mt5_client = mock_get_mt5_client.return_value
        mt5_client.get_account_overview.return_value = {
            "broker": "mt5",
            "mode": "disconnected",
            "accountNumber": None,
            "server": None,
            "currency": None,
            "isCentAccount": False,
            "balance": 0.0,
            "connected": False,
            "statusNote": "MT5 account unavailable.",
        }

        response = self.client.get("/api/v1/trading/broker")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("activeBroker", data)
        self.assertIn("brokers", data)
        self.assertIn("alpaca", data["brokers"])
        self.assertIn("mt5", data["brokers"])
        self.assertTrue(data["brokers"]["alpaca"]["connected"])
        self.assertIsNone(data["brokers"]["mt5"]["login"])
        self.assertFalse(data["brokers"]["mt5"]["connected"])
        self.assertEqual(data["brokers"]["mt5"]["balance"], 0.0)
        self.assertFalse(data["brokers"]["mt5"]["isCentAccount"])
        self.assertIn("Exness", data["brokers"]["mt5"]["name"])

        post_response = self.client.post(
            "/api/v1/trading/broker",
            {"broker": "mt5"},
            format="json",
        )
        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(post_response.json()["activeBroker"], "mt5")
