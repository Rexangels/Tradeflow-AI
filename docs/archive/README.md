# Archived Forex Trading Engine Roadmap

Archived on 2026-10-25 as a historical proposal, not an approved implementation plan.

## Review outcome

- The proposal's Gemini 4 Argon macro controller conflicts with the project constraint that Argon must not be used. Do not implement that provider/model choice.
- The proposal assumes a standalone local Python executor and SQLite trade log. The current project is a Django API with ORM-managed trade, signal, backtest, paper-trading, market-cache, and settings models; PostgreSQL is supported, with SQLite available for local development.
- Several proposed capabilities already have equivalents: MT5/Alpaca broker routing, risk checks, Forex strategy/regime/news/session services, scheduled market scans, trade journaling, and backtests with walk-forward and robustness diagnostics.
- Optuna tuning is not currently present. Any future optimizer should consume the existing journal/backtest contracts, run only on development data, and keep hard risk controls outside model/optimizer authority.
- The active architecture docs need reconciliation: README describes a crypto platform, while the implementation and Forex services are Forex-oriented. Update the canonical docs before treating this archived proposal as a roadmap.

See the project README, `PROFIT_SYSTEM.md`, `STRATEGY_RESEARCH.md`, and the Django `platform_api` models/services for current implementation context.
