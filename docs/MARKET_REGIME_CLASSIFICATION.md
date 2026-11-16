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

## Verification status

Classifier version `1.0.0`, its API/UI and the offline reviewed-label evaluator passed GitHub Actions on code commit `c79f74d5fcf79bf04e33d17206d1790f04b38e2a`: all 129 Django tests, frontend type-check, all frontend tests and production build passed. This verifies implementation behavior and test fixtures only; it does not establish that the regime rules predict profitable trades or generalize across markets. The human-label evaluator has been tested on synthetic test fixtures only; no real human-reviewed regime dataset has been supplied.

## Human-label evaluation workflow

The offline evaluator is available as:

```bash
python manage.py evaluate_market_regimes docs/regime_labels.csv --output reports/regime-evaluation.json
```

The CSV template at `docs/regime_labels_template.csv` contains the required header but intentionally contains no sample or generated labels. Fill it only after a reviewer has independently assigned the actual market regime for each symbol/timeframe/timestamp and the classifier output for that same completed bar has been recorded.

Required columns are `timestamp`, `symbol`, `timeframe`, `actual_regime`, `predicted_regime`, `classifier_version`, `feature_set_version`, and `label_source`. Use timezone-aware ISO-8601 timestamps, one row per unique symbol/timeframe/timestamp, and set `label_source` to `human_reviewed` only after a human has reviewed the actual label. The evaluator rejects generated labels as ground truth, duplicates, unsupported labels, missing versions, mixed classifier/feature versions, and naive timestamps.

The JSON report includes a confusion matrix, per-class precision/recall/F1, support, accuracy, macro-F1 and balanced accuracy. It evaluates classification agreement only. These metrics do not establish a trading edge, profitability, or future generalization. Use a separate chronologically held-out sample for out-of-sample evaluation; do not tune classifier thresholds against the same rows used to report final metrics.

## Validation still required

Before regime labels are used to gate strategy candidates, TradeFlow needs a time-aligned, independently reviewed labelled dataset, inter-annotator agreement where labels are subjective, per-class precision/recall, confusion matrices, stability tests across symbols/timeframes/providers, and out-of-sample/walk-forward evaluation. Threshold changes require a classifier version change and re-evaluation. No ML classifier should replace this baseline until its performance and calibration are shown to improve out of sample.
