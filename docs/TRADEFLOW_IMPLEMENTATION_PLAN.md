# TradeFlow AI — Autonomous Trading Intelligence Implementation Plan

**Status:** Approved direction; Phase 1 started  
**Working branch:** fix/micro-account-risk-and-execution-safety  
**Safety posture:** Research and paper trading only until explicit promotion gates pass.

## Objective

Evolve TradeFlow from a strategy/backtesting and broker-execution application into a guarded autonomous research and trading platform. It should understand market conditions, evaluate candidate strategies, abstain when no defensible opportunity exists, and execute only within independent deterministic risk controls.

Profitability is a hypothesis to test, not a feature to assume.

## Decisions and rationale

1. **Data-first before model-first.** Build trustworthy, timestamped historical data before introducing machine learning. Every downstream component depends on it.
2. **Separate research from execution.** Historical experiments, live observation, paper execution, supervised live execution and guarded autonomy are distinct modes with explicit promotion gates.
3. **Independent deterministic risk guardian.** Strategy models and LLMs may propose trades but cannot override risk rules, account verification, position limits or protective-order requirements.
4. **No-trade is a first-class outcome.** Abstain when data is stale or invalid, conditions are unclear, costs overwhelm expected edge or validation is weak.
5. **Version experiments.** Preserve data source, data window, strategy version, parameters, costs, metrics and validation results so results are reproducible.
6. **No self-promotion.** Strategies and autonomy levels require explicit operator approval.

## Target architecture

    MT5 / Alpaca / future provider adapters
                    |
                    v
          Canonical OHLCV contract
                    |
                    v
      Validation, provenance and freshness
                    |
                    v
      Historical datasets and snapshots
                    |
             Feature engineering
                    |
                    v
           Market regime classifier
                    |
                    v
       Strategy registry and evaluator
                    |
                    v
      Opportunity scorer / NO-TRADE
                    |
                    v
       Independent deterministic risk
                    |
                    v
          Paper / broker execution
                    |
                    v
      Orders, fills, costs and outcomes
                    |
                    v
       Research and human approval loop

The existing Django backend remains the system of record for users, agents, backtests, paper accounts, risk rules and trade logs. React remains the operator interface. Provider-specific parsing stays inside adapters; research components consume one canonical candle format. Avoid adding microservices or a message broker until measured scale justifies them.

## Phased implementation

### Phase 1 — Historical market-data foundation (current)
- Define a canonical OHLCV candle contract.
- Validate finite positive prices, OHLC geometry, finite non-negative volume, timezone-aware timestamps, strict chronological order and duplicates.
- Preserve source attribution: mt5, alpaca or synthetic_demo.
- Ensure completed-bar research never includes a forming candle.
- Validate provider responses before cache writes and cached payloads before reuse.
- Add freshness and expected-interval/gap diagnostics; never silently fill gaps.
- Persist reproducible dataset metadata: symbol, timeframe, provider, retrieval window, retrieval time, candle count, validation report and content hash.
- Add provider-adapter and cache tests.

**Exit criteria:** invalid or ambiguous data is rejected; synthetic data cannot enter strict research mode; source and timestamps are traceable; provider outages fail clearly; tests cover malformed, stale, duplicate and incomplete data.


**Current implementation status:** canonical candle validation, provider/cache validation, MT5 forming-bar exclusion, preliminary freshness/gap diagnostics, content-addressed `MarketDataSnapshot` persistence, owner-scoped snapshot retrieval, BacktestRun-to-snapshot linkage, and the React Market Data diagnostics view are implemented on the feature branch. GitHub Actions passed on commit `21a064c5`: backend dependency installation, Django system checks, migration-drift checks and all 105 backend tests; frontend type-check, tests and production build also passed. Phase 1 is functionally integrated. Remaining hardening is provider-session-aware freshness/gap interpretation and provider sandbox verification where available.

### Phase 2 — Feature engineering
Calculate returns, volatility, ATR, moving averages, momentum, volume statistics and spread/cost features. Make every feature causal: a timestamp may use only information available at that time. Version definitions and test against hand-calculated fixtures.


**First implementation slice verified (feature set v1.0.0):** a pure, deterministic feature engine computes per-bar returns (1/3/6/12), SMA-seeded EMA20/50/200, Wilder RSI14 and ATR14, ATR%, 20-return volatility, Bollinger width, trailing-20 volume z-score, candle range/body/close location, and optional explicitly supplied spread-cost inputs. Every row is causal; a prefix-vs-full-series test confirms future candles do not alter earlier values. EMA200 requires 200 bars; before that, the API returns `ready=false` with `abstainReason=insufficient_history`. Feature readiness is only a data warm-up condition, not a trade recommendation. Formula definitions and version are returned with the data. The authenticated `/market-data/features` API and Market Data UI are wired. GitHub Actions passed on code commit `5a89338b32cf0df7ae3c78c5c0100873a6dd2498`: all 114 Django tests, frontend type-check, frontend tests and production build passed.

### Phase 3 — Market-regime classification
Begin with transparent rules for trend, range, high volatility, low liquidity and uncertain markets. Build labelled evaluation sets and confusion matrices before comparing statistical or ML classifiers. Permit unknown/no-trade.


**Baseline classifier implemented and CI-verified; evaluation harness added, real labels pending:** `regime_classifier.py` v1.0.0 labels UPTREND, DOWNTREND, RANGE, HIGH_VOLATILITY or UNCERTAIN using explicit EMA/ATR structure and a trailing 90th-percentile volatility comparison over the preceding 100 bars (minimum 50 reference observations). Each timestamp is classified from itself and prior rows only. The API includes the rule version, threshold values, reason, underlying trend bias, and an explicit `executionAuthority=none`. Liquidity remains `not_assessed` because reliable, instrument-aware depth/spread evidence is not yet available. Tests cover the primary labels, insufficient history and future-bar invariance. GitHub Actions passed on code commit `dad0d78807fa17f92eddd3751a874dc83e7436ab`: all 121 Django tests plus frontend type-check, tests and production build. An offline evaluator and blank reviewed-label CSV template now produce confusion matrices and per-class precision/recall/F1 while rejecting model-generated labels and mixed versions. GitHub Actions passed on code commit `c79f74d5fcf79bf04e33d17206d1790f04b38e2a`: all 129 Django tests plus frontend type-check, frontend tests and production build. The evaluator is tested against synthetic test fixtures only; no real human-reviewed market labels have been supplied, so no empirical classifier score is claimed. Cross-symbol/timeframe validation and chronologically held-out testing remain mandatory before regime labels are allowed to gate strategies.

### Phase 4 — Strategy registry
Implement independently testable trend-following, breakout and mean-reversion candidates. Standardize entry, exit, stop, sizing interface and required market conditions. Strategies cannot call broker execution directly.

### Phase 5 — Backtesting and validation
Use chronological train/validation/test splits and walk-forward evaluation. Model spread, commission, slippage, financing, latency and realistic fills. Report expectancy, profit factor, drawdown, trade count, exposure, turnover and regime breakdown. Add sensitivity and Monte Carlo analysis and account for strategy-selection bias.

### Phase 6 — Opportunity scoring
Combine regime suitability, signal quality, expected net return, costs, uncertainty and validation evidence. Return TRADE, WAIT or NO_TRADE with structured reasons. The score is advisory; the Risk Guardian has final veto.

### Phase 7 — Live observation
Consume live completed bars without submitting orders. Record signal time, data snapshot, proposed entry/exit and subsequent outcome. Track prediction quality and divergence from historical expectations.

### Phase 8 — Paper execution
Route approved signals to paper execution only. Model spreads, slippage, partial fills, rejections, fees and stop execution. Reconcile internal orders and positions.

### Phase 9 — Supervised live and guarded autonomy
Resolve broker-native contract metadata, order-state reconciliation, protective-stop verification, daily equity drawdown, auth/CSRF and kill-switch blockers. Require human approval for every live order initially. Any constrained autonomy requires sustained evidence and explicit operator approval.

## Core measurements

- Data: source coverage, freshness, missing bars, duplicates, invalid OHLC, provider error rate.
- Strategy: net expectancy, profit factor, maximum drawdown, trade count, exposure, turnover and regime breakdown.
- Model: precision/recall, probability calibration, drift and abstention rate.
- Execution: spread, slippage, fill/rejection/partial-fill rates, protective-stop verification and reconciliation errors.
- Reliability: critical-control test coverage, incident rate and kill-switch behaviour.

## Current Phase 1 first slice

A provider-agnostic OHLCV validation contract and focused unit tests are being added first. This is not a claim that the full ingestion pipeline is complete. Next: integrate validation before cache writes and cache reads, remove the MT5 forming-bar fallback, and add freshness/gap/provenance checks.
