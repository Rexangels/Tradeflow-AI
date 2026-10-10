import type { Timeframe } from "../shared";

export const POPULAR_MARKETS = [
  // ── Spot Forex ──────────────────────────────────────────────
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
  // ── Crypto (24/7 on Exness MT5) ─────────────────────────────
  "BTC/USD",
  "ETH/USD",
  "SOL/USD",
  "XRP/USD",
  // ── Commodities ─────────────────────────────────────────────
  "XAU/USD",
  "XAG/USD",
] as const;

export const TIMEFRAME_OPTIONS: Timeframe[] = ["1m", "5m", "15m", "1h", "4h", "1d"];
