# TradeFlow AI

TradeFlow AI is now structured as a Django-backed crypto strategy research platform with a React frontend.

## Architecture

- `backend`: Django + Django REST Framework backend
- `frontend`: React 19 + Vite frontend
- `packages/shared`: shared TypeScript contracts used by the frontend

The active runtime no longer depends on Firebase. Auth, persistence, backtesting, paper trading, and AI orchestration now run through the Django API.

## What Works

- Single-admin session login with HTTP-only Django sessions
- Agent create/update flows
- Binance candle fetching with backend caching
- Deterministic backtests with saved runs and trade logs
- Paper trading with persisted balances, orders, and positions
- Backend AI chat orchestration with tool-style market/backtest context
- Routed frontend using React Router, TanStack Query, and Zustand

## Local Setup

1. Install frontend dependencies:
   `npm install`
2. Create a `.env` from `.env.example`
3. Install backend requirements:
   `.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt`
4. Run Django migrations:
   `.\.venv\Scripts\python.exe backend/manage.py migrate`
5. Start both apps:
   `npm run dev`

Frontend: [http://localhost:3000](http://localhost:3000)

Backend API: [http://localhost:4000/api/v1/health](http://localhost:4000/api/v1/health)

## Real Market Data

Keep `MARKET_DATA_FALLBACK_MODE=strict` for research, paper trading, and any
broker-connected workflow. In strict mode the platform refuses unavailable
market data instead of creating a synthetic series. Configure either a running
MT5 terminal (`MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`, optionally
`MT5_PATH`) or Alpaca credentials. The Market Data page identifies the provider
and verifies the latest bar; `GET /api/v1/market-data/status` exposes the same
read-only verification for a symbol and timeframe.

## Useful Commands

- Frontend type-check: `npm run lint --workspace @tradeflow/web`
- Frontend tests: `npm run test --workspace @tradeflow/web`
- Frontend build: `npm run build --workspace @tradeflow/web`
- Django checks: `.\.venv\Scripts\python.exe backend/manage.py check`
- Django tests: `.\.venv\Scripts\python.exe backend/manage.py test platform_api.tests`
- Create migrations: `.\.venv\Scripts\python.exe backend/manage.py makemigrations`

## Autonomous Trading and Micro Accounts

See [docs/AUTONOMOUS_TRADING_ROADMAP.md](docs/AUTONOMOUS_TRADING_ROADMAP.md) for the guarded-autonomy architecture, implemented safety changes, $10 paper-account configuration, research gates, and remaining production blockers.

See [docs/TRADEFLOW_IMPLEMENTATION_PLAN.md](docs/TRADEFLOW_IMPLEMENTATION_PLAN.md) for the full staged intelligence roadmap and [docs/MARKET_DATA_PIPELINE.md](docs/MARKET_DATA_PIPELINE.md) for Phase 1 data contracts and acceptance criteria.

For a $10 paper experiment, configure the PAPER_* variables in the backend environment before creating the paper account. Existing paper accounts retain their stored balances; changing PAPER_STARTING_BALANCE only affects newly created accounts. Keep MARKET_DATA_FALLBACK_MODE=strict for research and all broker-connected workflows.

**Do not use a $10 account for live execution yet.** Broker-specific minimum sizes, order-state reconciliation, protective-stop verification, and CSRF/session hardening still require validation. The MT5 adapter now rejects disconnected/fabricated account equity and refuses to upscale a position to meet minimum lot sizes.

## Postgres Note

The backend is written to accept a PostgreSQL `DATABASE_URL`. In this workspace it can also fall back to SQLite for quick local validation if `DATABASE_URL` is not set.

For production Postgres deployments, install a PostgreSQL driver such as `psycopg[binary]` in the Python environment.


## Research documentation
- [Market Regime Classifier & Evaluation](docs/MARKET_REGIME_CLASSIFICATION.md)
