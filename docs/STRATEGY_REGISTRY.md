# TradeFlow Strategy Registry

## Purpose

The strategy registry is the catalogue and compatibility boundary for research/backtest candidates. It gives each strategy a stable ID, version, engine, declared feature requirements, eligible market regimes, minimum history, and regime policy.

The registry is not an execution router. Every strategy contract declares `executionAuthority: none`. The registry does not submit orders, size live positions, override the Risk Guardian, or promote a strategy.

## Registered strategies

| ID | Version | Engine | Declared features | Eligible regimes | Minimum bars | Regime policy |
|---|---|---|---|---|---:|---|
| `trend-following` | `legacy-ema-cross/1.0` | `legacy` | EMA9, EMA21 | UPTREND, DOWNTREND | 30 | Advisory only |
| `mean-reversion` | `legacy-bollinger-rsi/1.0` | `legacy` | Bollinger20, RSI14 | RANGE | 30 | Advisory only |
| `trend-breakout-v1` | `trend-breakout-v1/1.0.0` | `trend_breakout_v1` | ATR14, EMA50, EMA200, multi-timeframe structure | UPTREND, DOWNTREND | 80 | Strategy internal |

The legacy trend-following and mean-reversion candidates currently share one legacy backtest engine. Their declared eligible regimes are metadata/advisory; they are not yet enforced as hard regime gates by the legacy engine. The trend-breakout candidate uses its own internal regime checks. This difference is explicitly surfaced in the Agent Builder.

The `trend-breakout` ID is retained as an alias for `trend-breakout-v1`.

## Resolution and validation rules

- Only enabled strategies are resolved for a backtest.
- An enabled ID must exist in the registry. Unknown enabled IDs are rejected.
- Aliases resolve to their canonical ID. Enabling the alias and canonical ID together is a duplicate and is rejected.
- Strategies that require different backtest engines cannot be selected in one run. The request is rejected rather than silently running only one engine.
- The request is validated before its dataset snapshot is written, so invalid strategy selections do not create orphan snapshots.
- The backtest response and stored validation payload include the exact strategy contract used for that run.
- The catalogue endpoint is read-only and authenticated: `GET /api/v1/strategies/catalog`.

## Current architecture boundary

`strategy_registry.py` is declarative. It resolves IDs to definitions and describes the selected research engine. The engine implementation remains in the existing backtest service. Strategy definitions cannot import or call broker clients, order execution, paper trading, or the Risk Guardian.

The independent deterministic Risk Guardian remains the only final authority for whether an order can proceed. The current strategy registry itself has no order permission.

## What is implemented and what remains

Implemented in this first registry slice:

- Stable IDs, versions, aliases and strategy metadata.
- Declared feature requirements, eligible regimes, minimum history and regime policy.
- Engine resolution and rejection of unknown/duplicate/mixed-engine selections.
- Strategy contract persistence with each backtest.
- Authenticated catalogue API and Agent Builder metadata display.
- Unit, API and frontend tests.

Still required in Phase 4:

- A shared strategy interface for causal feature input, entry/exit proposals, stop/target proposals, and research-only sizing assumptions.
- Separate independently testable strategy modules instead of routing multiple strategies through a shared legacy engine.
- Explicit validation of declared feature availability and minimum lookback per engine.
- Strategy-level regime suitability tests and per-regime backtest attribution.
- Versioned parameter schemas, immutable experiment configurations, and change-control rules.

The registry should not be interpreted as proof that the listed strategies have a positive expected return. The implementations remain experimental until their data, transaction-cost assumptions, robustness and chronological out-of-sample results are independently evaluated.
