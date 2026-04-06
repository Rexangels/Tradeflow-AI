import type { Timeframe } from "../shared";

export const POPULAR_MARKETS = [
  "ETHUSDT",
  "SOLUSDT",
  "XRPUSDT",
  "ADAUSDT",
  "DOGEUSDT",
  "AVAXUSDT",
  "BNBUSDT",
  "BTCUSDT",
] as const;

export const TIMEFRAME_OPTIONS: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];
