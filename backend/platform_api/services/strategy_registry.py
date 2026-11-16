"""Declarative registry for research and backtest strategy candidates.

Strategies describe what the research engine can evaluate. This registry does
not grant broker permission; every definition has execution_authority="none".
"""
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyDefinition:
    strategy_id: str
    name: str
    version: str
    description: str
    engine: str
    required_features: tuple[str, ...]
    eligible_regimes: tuple[str, ...]
    minimum_bars: int
    regime_policy: str
    implementation_status: str = "experimental"
    execution_authority: str = "none"
    aliases: tuple[str, ...] = ()


_DEFINITIONS = (
    StrategyDefinition(
        strategy_id="trend-following",
        name="Trend Following",
        version="legacy-ema-cross/1.0",
        description="Completed-bar EMA 9/21 crossover baseline.",
        engine="legacy",
        required_features=("ema9", "ema21"),
        eligible_regimes=("UPTREND", "DOWNTREND"),
        minimum_bars=30,
        regime_policy="advisory_only",
    ),
    StrategyDefinition(
        strategy_id="mean-reversion",
        name="Mean Reversion",
        version="legacy-bollinger-rsi/1.0",
        description="Bollinger-band and RSI mean-reversion baseline.",
        engine="legacy",
        required_features=("bollinger20", "rsi14"),
        eligible_regimes=("RANGE",),
        minimum_bars=30,
        regime_policy="advisory_only",
    ),
    StrategyDefinition(
        strategy_id="trend-breakout-v1",
        name="Trend Breakout",
        version="trend-breakout-v1/1.0.0",
        description="Multi-timeframe trend/breakout research engine with next-bar-open entries, ATR stops and targets.",
        engine="trend_breakout_v1",
        required_features=("atr14", "ema50", "ema200", "multi_timeframe_structure"),
        eligible_regimes=("UPTREND", "DOWNTREND"),
        minimum_bars=80,
        regime_policy="strategy_internal",
        aliases=("trend-breakout",),
    ),
)

_REGISTRY = {item.strategy_id: item for item in _DEFINITIONS}
_ALIAS_TO_ID = {
    alias: item.strategy_id
    for item in _DEFINITIONS
    for alias in item.aliases
}


def get_strategy_definition(strategy_id: str) -> StrategyDefinition:
    normalized = str(strategy_id or "").strip().lower()
    canonical = _ALIAS_TO_ID.get(normalized, normalized)
    try:
        return _REGISTRY[canonical]
    except KeyError as exc:
        raise ValueError(f"Unregistered strategy id: {normalized or '<empty>'}.") from exc


def resolve_enabled_strategies(agent: dict[str, Any]) -> list[StrategyDefinition]:
    strategies = agent.get("strategies", [])
    if not isinstance(strategies, list):
        raise ValueError("Agent strategies must be a list.")

    selected = []
    seen = set()
    for item in strategies:
        if not isinstance(item, dict):
            raise ValueError("Each agent strategy must be an object.")
        if not item.get("enabled"):
            continue
        definition = get_strategy_definition(item.get("id", ""))
        if definition.strategy_id in seen:
            raise ValueError(f"Strategy {definition.strategy_id} is enabled more than once.")
        seen.add(definition.strategy_id)
        selected.append(definition)

    engines = {item.engine for item in selected}
    if len(engines) > 1:
        raise ValueError(
            "Selected strategies use different backtest engines. "
            "Run each engine separately rather than silently ignoring a strategy."
        )
    return selected


def list_strategy_definitions() -> list[dict[str, Any]]:
    """Return stable JSON-compatible catalogue records for authenticated UI."""
    records = []
    for definition in _DEFINITIONS:
        record = asdict(definition)
        record["required_features"] = list(definition.required_features)
        record["eligible_regimes"] = list(definition.eligible_regimes)
        record["aliases"] = list(definition.aliases)
        record["execution_authority"] = "none"
        records.append(record)
    return records


def strategy_engine_for(agent: dict[str, Any]) -> str:
    selected = resolve_enabled_strategies(agent)
    return selected[0].engine if selected else "legacy"


def strategy_contract_for(agent: dict[str, Any]) -> dict[str, Any]:
    selected = resolve_enabled_strategies(agent)
    engine = selected[0].engine if selected else "legacy"
    return {
        "engine": engine,
        "strategies": [
            {
                "id": item.strategy_id,
                "version": item.version,
                "implementationStatus": item.implementation_status,
                "requiredFeatures": list(item.required_features),
                "eligibleRegimes": list(item.eligible_regimes),
                "minimumBars": item.minimum_bars,
                "regimePolicy": item.regime_policy,
                "executionAuthority": "none",
            }
            for item in selected
        ],
        "executionAuthority": "none",
    }
