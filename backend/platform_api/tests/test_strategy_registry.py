from django.test import SimpleTestCase

from platform_api.services.strategy_registry import (
    get_strategy_definition,
    list_strategy_definitions,
    resolve_enabled_strategies,
    strategy_contract_for,
    strategy_engine_for,
)


def agent_with(*enabled_ids):
    return {
        "strategies": [
            {"id": strategy_id, "enabled": True}
            for strategy_id in enabled_ids
        ]
    }


class StrategyRegistryTests(SimpleTestCase):
    def test_catalogue_is_stable_and_every_strategy_has_no_execution_authority(self):
        catalogue = list_strategy_definitions()
        ids = {item["strategy_id"] for item in catalogue}

        self.assertEqual(
            ids,
            {"trend-following", "mean-reversion", "trend-breakout-v1"},
        )
        self.assertTrue(all(item["execution_authority"] == "none" for item in catalogue))

    def test_existing_trend_following_and_mean_reversion_share_legacy_engine(self):
        agent = agent_with("trend-following", "mean-reversion")

        self.assertEqual(strategy_engine_for(agent), "legacy")
        self.assertEqual(
            [item.strategy_id for item in resolve_enabled_strategies(agent)],
            ["trend-following", "mean-reversion"],
        )

    def test_trend_breakout_alias_resolves_to_canonical_registry_entry(self):
        self.assertEqual(
            get_strategy_definition("trend-breakout").strategy_id,
            "trend-breakout-v1",
        )
        self.assertEqual(
            strategy_engine_for(agent_with("trend-breakout")),
            "trend_breakout_v1",
        )

    def test_mixed_backtest_engines_are_rejected_instead_of_silently_ignored(self):
        with self.assertRaisesRegex(ValueError, "different backtest engines"):
            strategy_engine_for(agent_with("trend-following", "trend-breakout-v1"))

    def test_unknown_enabled_strategy_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unregistered strategy id"):
            strategy_engine_for(agent_with("my-unknown-strategy"))

    def test_duplicate_canonical_strategy_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "enabled more than once"):
            strategy_engine_for(agent_with("trend-breakout", "trend-breakout-v1"))

    def test_disabled_unknown_strategy_is_not_resolved(self):
        agent = {"strategies": [{"id": "future-plugin", "enabled": False}]}

        self.assertEqual(strategy_engine_for(agent), "legacy")
        self.assertEqual(resolve_enabled_strategies(agent), [])

    def test_strategy_contract_explicitly_has_no_execution_authority(self):
        contract = strategy_contract_for(agent_with("trend-following"))

        self.assertEqual(contract["engine"], "legacy")
        self.assertEqual(contract["executionAuthority"], "none")
        self.assertEqual(contract["strategies"][0]["regimePolicy"], "advisory_only")
        self.assertEqual(contract["strategies"][0]["eligibleRegimes"], ["UPTREND", "DOWNTREND"])
