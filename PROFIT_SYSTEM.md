# TradeFlow AI — Profit-System Design (Expectancy, Not Certainty)

> This system does not predict winners. It takes many small, well-defined
> losing bets so that fewer bigger winners pay for them after all costs.

## 1. Why the old gate always said WAIT

The old swing gate required H4 bias + H1 confirm + M15 trigger + confidence
≥ 0.55 + 2pt margin + news CLEAR + session OK, all at once. Most bars are
chop/range, so the default output was WAITING / RANGING / CONFLICTED. That is
correct for a pure trend system — but it means zero base rate and no learning.

Forcing trades through that gate in chop = buying noise. The fix is not a
looser gate. It is separate modules + a regime switch + measured expectancy.

## 2. Signal vs permission

- **Signals vote.** Each family is independent and backtested alone:
  - `trend`: H4 EMA50/200 stack + price location (`trend_breakout.py`)
  - `momentum`: M15 EMA9/21 cross + RSI 40–60 + MACD hist flip
  - `breakout`: Donchian-20 close beyond range + ATR-percentile expansion
  - `mean_reversion`: BB touch + RSI exhaustion (range only, never blended)
  - `liquidity`: London/NY overlap boost, rollover veto (`session_filter.py`)
  - `news`: live ForexFactory-mirror veto (`economic_calendar.py`)
- **Permission gates.** `regime.py:classify_regime` returns
  `trending | ranging | volatility_expansion | news_blocked | rollover`.
  Trending → trend module only. Ranging → mean-reversion only or flat.
  News/rollover/vol-expansion → flat. One function drives scanner,
  backtester, paper, and live.

## 3. Scoring: grades, not confidence

`composite_score` 88/72/50/35 was hardcoded. Treat it as an alignment grade.
Real confidence comes from the journal:

- Every backtest exit records MFE/MAE (max favorable/adverse excursion),
  SL/TP distance, regime, session, and costs.
- Every live `AISignal.indicators` stores the same vote vector.
- Calibrate buckets: "score 70–75 on GBP/USD London = 42% hit 2R over N=300".
- `model_analysis.py` must predict **trade outcome** (hit 2R before SL),
  not next-bar direction.

## 4. Expectancy math (the only profit formula)

For each module alone report: trades, win%, avg win/loss, profit factor,
expectancy, maxDD, exposure, Sharpe, walk-forward beat rate.

- Prefer 35–45% win × 2R over 70% win × 0.5R (spread kills the latter).
- Risk per trade `riskPct` 0.005–0.02, size = min(capital fraction,
  riskCapital / SL distance). Never scale by "AI confidence".
- Max 1–2 concurrent trend positions (correlated), -50% size on intraday
  contra-H4 `CAUTION`, no second entry same direction same day.
- Promote only on: positive expectancy after all costs, enough trades,
  stable walk-forward, paper matches backtest fills.

## 5. AI role: narrator + watchdog

LLM explains, ranks, and flags. It never invents entries or overrides a veto.

- Explain the vote tally once, in ≤220 words.
- Rank the 11-pair scan by expectancy bucket, not RSI.
- Flag anomalies: 3 consecutive SLs, vol regime flip, journal drift.
- `OrderExecutionService.execute_order` requires `RiskManager` approval;
  `bypass_risk` is manual-only and logged. Auto-trades must link
  `signal_id` → `AISignal` → `TradeLog`.

## 6. Scheduler: automate the wait

`scan_markets` runs on M15 close (:01, :16, :31, :46), scans
`DEFAULT_SCAN_UNIVERSE`, writes `AISignal` only on False→True flips, stores
last state in `AppSetting(scan_state)`, respects news/session gates.
Frontend `AISignalsFeed` polls `/signals` and toasts new TRADEABLEs.
The job does not create edge — it measures base rate
("2.3 TRADEABLE/week/pair") so you know in 4 weeks if edge exists.

## 7. Files

- `backend/platform_api/services/regime.py` — single regime classifier
- `backend/platform_api/services/trend_breakout.py` — votes + breakout
- `backend/platform_api/services/backtests.py` — MFE/MAE, sensitivity,
  Monte Carlo, per-module diagnostics in `validation`
- `backend/platform_api/services/order_execution.py` — risk gate + signal link
- `backend/platform_api/management/commands/scan_markets.py` — scheduled scan
- `frontend/src/components/trading/AISignalsFeed.tsx` — toast on new signal

## 8. What NOT to do

- Do not blend trend + mean-reversion scores.
- Do not trade synthetic_demo data (blocked in backtest + execution).
- Do not optimize parameters until rules, costs, and data source are frozen.
- Do not go live on one good backtest. Require walk-forward + paper match.
