# TradeFlow Market Regime Classifier

## Status and purpose

The initial rule-based classifier is an experimental research layer, version `1.0.0`. Its only job is to describe the observed market environment. It does not identify a complete trade setup, calculate position size, approve risk, or submit orders. Its response always reports `executionAuthority: none`.

The classifier consumes the versioned causal feature payload from `platform_api.services.feature_engine`. It does not fetch prices or call a broker itself.

## Labels

- `UPTREND`: EMA20 > EMA50 > EMA200, close above EMA200, and positive 12-bar return.
- `DOWNTREND`: EMA20 < EMA50 < EMA200, close below EMA200, and negative 12-bar return.
- `RANGE`: fast EMA separation no greater than 0.5 ATR, slow EMA separation no greater than 1.5 ATR, and absolute 12-bar return no greater than 3 ATR percentages.
- `HIGH_VOLATILITY`: current 20-bar return volatility exceeds the nearest-rank 90th percentile of the preceding 100 valid volatility observations. At least 50 historical observations are required. High volatility overrides the primary regime label, but the underlying `trendBias` is still reported.
- `UNCERTAIN`: feature warm-up is incomplete or the latest market structure does not satisfy any label's rules.

All thresholds are returned in the API response so evaluations can identify the rule version and parameters used.

## Causality

Classification at bar `i` reads feature row `i` and no later row. The high-volatility reference window ends at `i - 1`; the current bar is compared with the previous observations and is not included in its own threshold. A prefix-versus-full-series test checks that appending future bars does not change a prior classification.

## Liquidity and execution boundaries

Liquidity is deliberately reported as `not_assessed`. Raw volume is not comparable across all instruments and providers, and this application does not yet have a validated, instrument-aware market-depth/spread model. A high raw volume or a low z-score is not enough to claim that a market is liquid or illiquid.

The classifier has no execution permission. Regime labels are not buy/sell/hold recommendations and do not constitute a validated trading edge. A future Opportunity Scoring layer must combine strategy evidence, transaction costs, uncertainty and independent Risk Guardian checks. Until that layer exists, an `UNCERTAIN` classification is an explicit abstention; a clear trend or range still does not authorize a trade.

## Validation still required

Before regime labels are used to gate strategy candidates, TradeFlow needs a time-aligned, independently reviewed labelled dataset, inter-annotator agreement where labels are subjective, per-class precision/recall, confusion matrices, stability tests across symbols/timeframes/providers, and out-of-sample/walk-forward evaluation. Threshold changes require a classifier version change and re-evaluation. No ML classifier should replace this baseline until its performance and calibration are shown to improve out of sample.
