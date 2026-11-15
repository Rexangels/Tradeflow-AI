# Autonomous Trading Roadmap and Micro-Account Safety

## Product direction

TradeFlow AI is intended to become a guarded autonomous trading system that can:

1. Observe market data and identify the current market regime.
2. Research and compare deterministic strategy candidates.
3. Select only strategies that pass pre-defined validation gates.
4. Size positions from verified broker equity and instrument constraints.
5. Execute through a broker adapter with protective orders.
6. Monitor open risk, reconcile broker state, and stop when safety conditions fail.
7. Record every signal, decision, order, fill, cost, and outcome for continuous evaluation.

The AI layer may explain, classify, compare, and recommend. It must never override deterministic risk limits, fabricate broker/account state, or silently remove protective order instructions.

## Implemented in this change

- Risk defaults are more conservative: 1% maximum planned risk per trade, one open position, and a 2% daily loss threshold.
- Missing, disconnected, zero, or unverified broker equity now rejects a new order instead of falling back to a fabricated $500 account.
- Failure to retrieve open positions rejects a new order rather than silently skipping exposure checks.
- Daily risk checks include negative unrealized P&L from currently open broker positions as well as realized losses recorded today.
- MT5 sizing rounds down to the supported volume step and rejects orders below the broker's minimum. The system no longer increases a position to 0.01 lots to force execution.
- The MT5 disconnected/demo placeholder no longer reports a made-up $15 cent-account balance. It reports zero equity and connected=false.
- Alpaca bracket/protected orders are never retried as ordinary unprotected orders after a broker rejection.
- Paper-account starting balance and risk limits can be configured independently through environment variables.
- Paper daily loss monitoring includes current negative unrealized P&L, and the daily loss gate does not prevent a sell that reduces or closes an existing long position.
- Django now defaults to DEBUG=false and requires an explicit DJANGO_SECRET_KEY outside debug mode.
- Regression tests cover MT5 minimum-volume handling and disconnected account reporting.

## $10 micro-account paper configuration

Set these values in the backend environment for an isolated $10 paper-account experiment:

```dotenv
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<generate-a-long-random-secret>
MARKET_DATA_FALLBACK_MODE=strict

PAPER_STARTING_BALANCE=10
PAPER_MAX_ORDER_NOTIONAL=1
PAPER_MAX_OPEN_POSITIONS=1
PAPER_MAX_DAILY_LOSS=0.20
PAPER_TRADING_ENABLED=true
```

The $1 notional cap limits each new paper buy to 10% of the starting account, while the $0.20 daily loss threshold represents 2% of the starting balance. These are conservative experiment settings, not a promise that a broker can execute comparable live orders.

Paper trading currently models long spot-style positions with fixed fee and slippage assumptions. It is not a substitute for a broker-specific MT5/Alpaca simulation, and the paper account does not yet model broker minimum lots, margin, funding, partial fills, or stop-loss execution.

## Autonomy levels

| Level | Description | Promotion condition |
|---|---|---|
| 0 — Observe | Collect market data and classify regimes; no orders | Data source and timestamp quality verified |
| 1 — Research | Backtest and compare strategy candidates | No look-ahead; fees/spread/slippage included |
| 2 — Paper | Execute simulated orders and monitor risk | Forward results across multiple regimes |
| 3 — Supervised live | Human approves each live order | Broker reconciliation and protective-order verification |
| 4 — Guarded autonomy | Bot can execute within hard risk limits | Independent audit, kill-switch tests, and sustained forward evidence |

TradeFlow must not promote itself automatically between levels. Promotion requires explicit operator approval.

## Strategy selection and research gates

The intended strategy selector should choose among trend-following, breakout, and mean-reversion only when the current regime is sufficiently clear. It should return **no trade** when signals conflict, data is stale, spread is abnormal, or validation is weak.

Before a strategy can be promoted from research to paper or live execution, record:

- Versioned strategy rules and immutable parameter set.
- In-sample, validation, and untouched out-of-sample results.
- Walk-forward windows and regime breakdown.
- Trade count, expectancy, profit factor, win rate, maximum drawdown, and exposure.
- Realistic spread, commissions, slippage, financing, and rejected/partial order assumptions.
- Monte Carlo path distribution and parameter sensitivity.
- Forward paper-trading results and divergence from simulated fills.

A high win rate alone is not evidence of an edge. No strategy should be called profitable until its net results are independently reproduced.

## Remaining production blockers

The following items are not claimed as completed by this change:

1. Replace the legacy CSRF-exempt session authentication with standard CSRF-protected session auth and verify the frontend login/request flow.
2. Add broker-native symbol metadata discovery for every MT5 instrument, including contract size, volume step, tick value, stop distance, and account currency conversion.
3. Add broker order-state reconciliation for accepted, partial, rejected, cancelled, and filled orders.
4. Verify protective stop placement after entry and continuously monitor broker-side stop status.
5. Build an equity-based daily drawdown baseline at the start of each broker-local trading day, including commissions, swaps, and fees.
6. Add automated tests for Alpaca protected-order rejection, risk-manager fail-closed behavior, and paper-account risk limits.
7. Run the Django test suite and broker sandbox tests in a configured development environment before merging.

**Live trading remains disabled for the $10 experiment until these blockers are resolved and forward paper results are reviewed.**
