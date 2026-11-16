# Phase 1 — Historical Market Data Pipeline

## Purpose

Create a trustworthy historical data layer for backtesting, feature engineering, regime classification and strategy research. A strategy result is meaningful only when its input data is valid, ordered, attributable and reproducible.

## Existing application baseline

The Django backend already fetches candles from MT5, then Alpaca, and optionally synthetic demo data. It caches candle batches by symbol, timeframe and limit in MarketDataCache and exposes candle retrieval and a market-data status endpoint.

This is a useful starting point, but a cache and provider fallback are not a research-grade data pipeline. The next work establishes validation, provenance, freshness and reproducibility around the existing service rather than replacing the backend.

## Canonical candle contract

Each candle contains:
- time: ISO-8601 timestamp with explicit timezone; UTC preferred.
- open, high, low, close: finite positive numbers.
- volume: finite non-negative number.
- source: explicit provider identifier such as mt5, alpaca or synthetic_demo.

Rules:
1. Bars are strictly ordered oldest to newest.
2. Duplicate timestamps are invalid.
3. High is at least open, close and low.
4. Low is no greater than open, close and high.
5. Missing or malformed values are rejected, never silently filled.
6. Completed-bar research excludes still-forming candles.
7. Synthetic demo data is never mistaken for real provider data or accepted in strict research mode.

## Pipeline stages

1. Acquire: provider adapter fetches requested symbol, timeframe and window.
2. Normalize: provider-specific fields and timestamps become the canonical shape.
3. Validate: schema, numeric values, OHLC geometry, ordering, duplicates and freshness.
4. Attribute: preserve provider, retrieval time, symbol, timeframe and session/adjustment metadata.
5. Cache/store: cache only validated batches; persist dataset metadata alongside research snapshots.
6. Serve: API exposes candles and clear availability/provenance metadata.
7. Audit: record validation failures and provider errors without exposing credentials.

## Data quality diagnostics

Report candle count, first/last timestamps, source, retrieval/check time, stale latest-bar status, duplicates, out-of-order bars, missing intervals and invalid OHLC/volume counts, plus synthetic-vs-real status.

A gap is a diagnostic, not automatically an error: weekends, holidays, exchange closures and provider session calendars can explain missing intervals. Never fabricate candles to fill gaps. Research jobs must explicitly decide whether a dataset with gaps is acceptable.

## Storage evolution

Keep Django and MarketDataCache for short-lived request caching. For research-grade history, add a separate append-only dataset/snapshot concept instead of treating a cache row as permanent history. A snapshot identifies symbol, timeframe, provider, start/end, candle count, retrieval time, validation report and content hash. Start with existing Django/Postgres infrastructure; do not add a time-series database until volume and query benchmarks justify it.

## Acceptance tests

- Valid chronological OHLCV data passes.
- Empty, malformed, non-finite, non-positive or impossible OHLC data fails.
- Negative volume fails.
- Naive timestamps, duplicate timestamps and out-of-order bars fail.
- A forming MT5 bar is never silently substituted for a completed bar.
- Invalid provider data is not cached.
- Invalid or stale cached data is not served to research.
- Synthetic data is explicitly labelled and blocked in strict mode.
- Provider outage returns an explicit unavailable result, not invented prices.

## Implementation progress

Implemented on the current feature branch:
- Reusable canonical OHLCV validator and focused unit tests.
- Validation before provider data is cached and validation before cached payloads are reused.
- Invalid provider payloads are rejected and not cached; invalid cached payloads are ignored and refreshed from a provider.
- MT5 no longer falls back from the last completed candle (position 1) to position 0 when no completed candle is returned.
- A non-destructive quality-report helper reports approximate freshness and interval gaps. Gap estimates are diagnostic only because exchange/session calendars are not yet applied.
- Integration tests cover valid provider caching, invalid provider rejection, invalid-cache refresh, diagnostics, and MT5 forming-bar exclusion.

Still outstanding before Phase 1 is complete:
- Expose quality diagnostics through the market-data status/API response and frontend.
- Add provider-specific freshness/session-calendar handling and stronger incomplete-window diagnostics.
- Persist reproducible historical dataset snapshots and content hashes (separate from the short-lived cache).
- Run the new tests and the broader Django suite; add provider sandbox verification where available.

The new and existing tests have been written but have not yet been executed in this environment.
