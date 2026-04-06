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

## Useful Commands

- Frontend type-check: `npm run lint --workspace @tradeflow/web`
- Frontend tests: `npm run test --workspace @tradeflow/web`
- Frontend build: `npm run build --workspace @tradeflow/web`
- Django checks: `.\.venv\Scripts\python.exe backend/manage.py check`
- Django tests: `.\.venv\Scripts\python.exe backend/manage.py test platform_api.tests`
- Create migrations: `.\.venv\Scripts\python.exe backend/manage.py makemigrations`

## Postgres Note

The backend is written to accept a PostgreSQL `DATABASE_URL`. In this workspace it can also fall back to SQLite for quick local validation if `DATABASE_URL` is not set.

For production Postgres deployments, install a PostgreSQL driver such as `psycopg[binary]` in the Python environment.
