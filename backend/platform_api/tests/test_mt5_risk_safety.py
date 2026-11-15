from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase, override_settings

from platform_api.models import RiskRule
from platform_api.services.risk_manager import RiskManager

from platform_api.services.mt5_client import MT5Client, normalise_mt5_volume


class MT5VolumeSafetyTests(SimpleTestCase):
    def test_rejects_volume_below_broker_minimum(self):
        info = SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)
        with self.assertRaisesRegex(ValueError, "below broker minimum"):
            normalise_mt5_volume(0.005, info)

    def test_rounds_down_to_volume_step_without_upscaling(self):
        info = SimpleNamespace(volume_min=0.01, volume_max=100.0, volume_step=0.01)
        self.assertEqual(normalise_mt5_volume(0.019, info), 0.01)

    def test_rejects_volume_above_broker_maximum(self):
        info = SimpleNamespace(volume_min=0.01, volume_max=1.0, volume_step=0.01)
        with self.assertRaisesRegex(ValueError, "exceeds broker maximum"):
            normalise_mt5_volume(1.1, info)

    def test_rejects_non_positive_or_non_finite_volume(self):
        for volume in (0, -0.01, float("nan"), float("inf")):
            with self.subTest(volume=volume):
                with self.assertRaisesRegex(ValueError, "finite positive"):
                    normalise_mt5_volume(volume)

    def test_disconnected_account_never_reports_a_fabricated_balance(self):
        client = MT5Client(login=None, password="", server="offline-test")
        account = client._simulated_account_overview(error="offline")
        self.assertFalse(account["connected"])
        self.assertEqual(account["equity"], 0.0)
        self.assertEqual(account["balance"], 0.0)
        self.assertEqual(account["mode"], "disconnected")


class MicroAccountRiskProfileTests(TestCase):
    @override_settings(TRADEFLOW_MICRO_ACCOUNT_MODE=True)
    def test_micro_mode_caps_stale_database_risk_rules(self):
        RiskRule.objects.create(key="max_risk_pct", value={"value": 5.0})
        RiskRule.objects.create(key="max_positions", value={"value": 8})
        RiskRule.objects.create(key="daily_loss_limit_pct", value={"value": 10.0})
        RiskRule.objects.create(key="max_position_pct", value={"value": 50.0})
        RiskRule.objects.create(key="min_rr_ratio", value={"value": 1.0})
        RiskRule.objects.create(key="require_stop_loss", value={"value": False})

        rules = RiskManager.get_all_rules()

        self.assertEqual(rules["max_risk_pct"], 1.0)
        self.assertEqual(rules["max_positions"], 1)
        self.assertEqual(rules["daily_loss_limit_pct"], 2.0)
        self.assertEqual(rules["max_position_pct"], 10.0)
        self.assertEqual(rules["min_rr_ratio"], 1.5)
        self.assertTrue(rules["require_stop_loss"])
