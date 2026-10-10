import type { Timeframe } from "../shared";

export const POPULAR_MARKETS = [
  "EUR/USD",
  "GBP/USD",
  "USD/JPY",
  "AUD/USD",
  "USD/CAD",
  "USD/CHF",
  "NZD/USD",
  "EUR/GBP",
  "EUR/JPY",
  "GBP/JPY",
] as const;

export const TIMEFRAME_OPTIONS: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];
