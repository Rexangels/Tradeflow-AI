# TradeFlow AI Strategy Research Plan

## Purpose

TradeFlow AI is being built as a disciplined strategy-research and execution
platform. Its purpose is not to claim that an LLM can predict markets. The
platform should identify objectively defined conditions, calculate risk,
execute only when permitted, and measure every result against real data.

This document records the intended strategy architecture and the standards a
strategy must meet before it can progress from research to paper trading or
live capital.

## Current System

The platform already provides these building blocks:

- H4, H1, and M15 top-down confluence analysis.
- EMA, RSI, MACD, ATR, and Bollinger Band calculations.
- Session/liquidity and rollover filters.
- A news-shield rule framework.
- Stop-loss, reward-to-risk, position-count, position-size, and daily-loss
  guardrails.
- MT5 and Alpaca broker adapters, paper trading, backtests, and trade logs.
- Market-data provenance: MT5, Alpaca, and synthetic demo data are labelled.
  Synthetic candles cannot validate a strategy or route an order.

The current confluence engine is a research hypothesis, not a demonstrated
edge. It must be tested using real historical data and realistic costs.

## Operating Principle

The system is rules-first and AI-assisted.

```text
Real market data
        |
Market-regime classifier
        |
Approved strategy module
        |
News, session, and liquidity filters
        |
Risk manager and broker constraints
        |
Paper/live execution and audit journal
        |
AI explanation, ranking, and anomaly review
```

AI may explain an approved setup, rank approved opportunities, flag an
anomaly, summarize news, and help review journal data. AI must not invent a
trade, override a hard risk rule, or present untested confidence as proof of
an edge.

## Candidate Strategy Modules

Each module must be implemented, tested, and measured independently before it
is combined with another module.

### 1. Trend / Breakout Module (first priority)

**Use when:** the market is trending or breaking from a compressed range.

**Initial hypothesis:** trade in the direction of the higher-timeframe trend,
enter only after a lower-timeframe breakout or pullback confirmation, and use
ATR-based stops and volatility-adjusted position sizing.

**Inputs:**

- H4 trend direction and structure.
- H1 confirmation and trend strength.
- M15 breakout, pullback, or close beyond a defined range.
- ATR, spread, session, and news state.

**Controls:**

- No counter-trend entry.
- No entry during major-news buffer or poor-liquidity periods.
- Stop-loss and take-profit must be broker-valid and entered with the trade.
- One formal rule set must drive scanning, backtesting, paper trading, and
  broker execution.

**Why research it:** time-series momentum/trend following has substantial
historical academic evidence across liquid futures, including currencies. This
is evidence for investigation, not a guarantee that a particular FX broker,
timeframe, or implementation will be profitable.

### 2. Range Mean-Reversion Module (second priority)

**Use when:** the market is demonstrably ranging, not trending or expanding in
volatility.

**Initial hypothesis:** fade defined range extremes using Bollinger/RSI and a
clear invalidation point; exit at the mean or opposing range boundary.

**Required regime gates:**

- H4 must not show a strong directional trend.
- ATR/volatility expansion must be absent.
- Spread and session conditions must be acceptable.
- The module must be disabled before high-impact news.

This must remain separate from trend following. A mean-reversion signal during
a strong trend is a different trade and must not be hidden inside a blended
score.

### 3. FX Carry / Macro Bias (research later)

**Use when:** the platform has reliable interest-rate, swap, and macro data.

Carry is primarily a higher-timeframe portfolio factor, not an M15 entry
signal. It may contribute to an H4/H1 bias, but its tail-risk behaviour must
be understood and tested. It should not be added until the first two modules
are validated.

## Market-Regime Classifier

The classifier chooses the permitted strategy family; it does not predict
price. Initial states:

| Regime | Permitted action |
| --- | --- |
| Trending | Trend / breakout module only |
| Ranging | Mean-reversion module only |
| Volatility expansion or major news | No new trade |
| Low liquidity, rollover, or invalid data | No new trade |

Initial regime inputs may include H4/H1 EMA slope and separation, ADX or a
similarly defined trend-strength measure, ATR percentile/expansion, and range
breakout state. Exact thresholds must be selected without looking at the final
test period.

## Data and Execution Requirements

A result is not eligible for a strategy decision unless it records:

- Provider and source (`mt5` or `alpaca`), symbol mapping, timeframe, and bar
  timestamps.
- Bid/ask or a documented spread model.
- Commission, swap/funding, and slippage assumptions.
- The strategy and parameter version used.
- Entry, stop, target, actual fill, broker response, and final P&L.

Synthetic data is permitted only for user-interface demonstrations. It is not
eligible for validation, paper-trading promotion, or live order routing.

## Backtesting Standard

Every strategy module must be evaluated with:

1. Real historical data only.
2. Signal generation on a completed bar and entry at the next tradable price.
3. Bid/ask spread, variable slippage, commissions, swaps/funding, and realistic
   stop/target behaviour.
4. Correct FX contract size, pip/tick value, account-currency conversion,
   leverage, and minimum volume rules.
5. Separate development, validation, and locked out-of-sample periods.
6. Walk-forward tests across multiple market regimes and relevant symbols.
7. Sensitivity tests around parameters and Monte Carlo or trade-order
   perturbation tests.

Do not optimise a strategy until its rules, costs, and data source are stable.

## Promotion Gates

Thresholds must be finalised before reviewing the locked test set. A module may
advance only when all applicable gates are satisfied:

| Stage | Minimum evidence |
| --- | --- |
| Research | Explicit rules, real data, reproducible backtest |
| Candidate | Positive expectancy after all costs; enough trades to be meaningful; stable behaviour across walk-forward windows |
| Paper trading | Acceptable maximum drawdown, profit factor, and out-of-sample behaviour; no unresolved execution or data-source defects |
| Limited live capital | Paper performance reasonably matches expected fill/cost behaviour; broker reconciliation, alerts, and kill switch are verified |

Metrics to record: number of trades, win rate, average win/loss, expectancy,
profit factor, maximum drawdown, exposure, Sharpe/Sortino where appropriate,
and performance by symbol, session, regime, and news exposure.

No single metric is enough. High win rate can coexist with large rare losses;
high backtest Sharpe can be an artifact of incorrect fills or overfitting.

## Planned Implementation Order

1. Connect and verify real MT5 or Alpaca market data for the selected symbols.
2. Formalise the current H4/H1/M15 setup as the trend/breakout module.
3. Upgrade the backtester to execute the same module with realistic fills and
   costs.
4. Integrate a live economic-calendar provider and test the news filter.
5. Add a regime classifier and build the separate range mean-reversion module.
6. Run walk-forward validation, then several weeks of paper trading.
7. Add carry/macro research only after the first modules meet their gates.

## Research References

- Moskowitz, Ooi, and Pedersen, *Time Series Momentum*, Journal of Financial
  Economics (2012): https://doi.org/10.1016/j.jfineco.2011.11.003
- Asness, Moskowitz, and Pedersen, *Value and Momentum Everywhere*, Journal of
  Finance (2013): https://doi.org/10.1111/jofi.12021
- Hurst, Ooi, and Pedersen, *A Century of Evidence on Trend-Following
  Investing*: https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf
- Bank for International Settlements, *Monetary policy transmission to exchange
  rates: the role of currency carry trades*:
  https://www.bis.org/publications/bulletin-124-monetary-policy-transmission-exchange-rates-role-currency-carry-trades

These studies motivate research directions; they do not establish that TradeFlow
AI, a specific broker, or a particular parameter set will be profitable.
