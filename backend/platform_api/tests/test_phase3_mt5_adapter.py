from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from platform_api.services.mt5_client import MT5Client, get_mt5_client
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

    def test_mt5_client_initialization(self):
        client = MT5Client(login=477536967, server="Exness-MT5Trial9")
        self.assertEqual(client.login, 477536967)
        self.assertEqual(client.server, "Exness-MT5Trial9")

        overview = client.get_account_overview()
        self.assertEqual(overview["broker"], "mt5")
        self.assertEqual(overview["mode"], "demo")
        self.assertEqual(overview["accountNumber"], "477536967")
        self.assertTrue(overview["isCentAccount"])

    def test_broker_switching(self):
        # Default can be switched to mt5
        active = OrderExecutionService.set_active_broker("mt5")
        self.assertEqual(active, "mt5")
        self.assertEqual(OrderExecutionService.get_active_broker(), "mt5")

        overview = OrderExecutionService.get_account_overview()
        self.assertEqual(overview["broker"], "mt5")
        self.assertEqual(overview["accountNumber"], "477536967")

        # Switch back to alpaca
        active_alpaca = OrderExecutionService.set_active_broker("alpaca")
        self.assertEqual(active_alpaca, "alpaca")
        self.assertEqual(OrderExecutionService.get_active_broker(), "alpaca")

    def test_active_broker_api_endpoint(self):
        resp = self.client.get("/api/v1/trading/broker")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("activeBroker", data)
        self.assertIn("brokers", data)
        self.assertIn("alpaca", data["brokers"])
        self.assertIn("mt5", data["brokers"])
        self.assertEqual(data["brokers"]["mt5"]["login"], "477536967")
        self.assertIn("Exness", data["brokers"]["mt5"]["name"])

        # POST to toggle broker
        post_resp = self.client.post("/api/v1/trading/broker", {"broker": "mt5"}, format="json")
        self.assertEqual(post_resp.status_code, 200)
        self.assertEqual(post_resp.json()["activeBroker"], "mt5")
