import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketDataPage } from "./market-data-page";


describe("MarketDataPage", () => {
  it("shows validated-feed diagnostics and saved dataset fingerprints", async () => {
    const candles = [
      {
        time: "2026-11-16T09:00:00+00:00",
        open: 1.1,
        high: 1.101,
        low: 1.099,
        close: 1.1005,
        volume: 900,
        source: "mt5",
      },
      {
        time: "2026-11-16T10:00:00+00:00",
        open: 1.1005,
        high: 1.102,
        low: 1.1,
        close: 1.1015,
        volume: 1100,
        source: "mt5",
      },
    ];
    const contentSha256 = "a".repeat(64);

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/market-data/features")) {
          return new Response(
            JSON.stringify({
              featureSetVersion: "1.0.0",
              symbol: "EURUSD",
              timeframe: "1h",
              source: "mt5",
              asOf: "2026-11-16T10:00:00+00:00",
              barCount: 220,
              requiredBars: 200,
              warmupBars: 0,
              ready: true,
              abstainReason: null,
              latest: {
                return1Pct: 0.1,
                return3Pct: 0.3,
                return6Pct: 0.6,
                return12Pct: 1.2,
                ema20: 1.100,
                ema50: 1.095,
                ema200: 1.080,
                ema20Vs50Pct: 0.46,
                ema50Vs200Pct: 1.39,
                closeVsEma200Pct: 1.85,
                rsi14: 62.5,
                atr14: 0.0012,
                atrPct: 0.11,
                volatility20Pct: 0.08,
                bollingerWidth20Pct: 0.62,
                volumeZScore20: 1.25,
                candleRangePct: 0.13,
                candleBodyPct: 0.05,
                closeLocation: 0.7,
                spreadPips: null,
                spreadCostPct: null,
              },
              series: [],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/market-data/candles")) {
          return new Response(JSON.stringify(candles), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (url.includes("/market-data/status")) {
          return new Response(
            JSON.stringify({
              available: true,
              symbol: "EURUSD",
              timeframe: "1h",
              source: "mt5",
              isRealData: true,
              latestBarTime: "2026-11-16T10:00:00+00:00",
              checkedAt: "2026-11-16T10:01:00+00:00",
              quality: {
                valid: true,
                count: 2,
                first_time: "2026-11-16T09:00:00+00:00",
                last_time: "2026-11-16T10:00:00+00:00",
                source: "mt5",
                timeframe: "1h",
                checked_at: "2026-11-16T10:01:00+00:00",
                latest_bar_age_seconds: 60,
                freshness_threshold_seconds: 10800,
                freshness: "recent",
                gap_count: 0,
                missing_intervals_estimate: 0,
                gap_policy: "diagnostic_only_market_calendar_not_applied",
              },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/market-data/snapshots")) {
          return new Response(
            JSON.stringify([
              {
                id: "snapshot-1",
                symbol: "EURUSD",
                timeframe: "1h",
                source: "mt5",
                firstBarAt: "2026-11-16T09:00:00+00:00",
                lastBarAt: "2026-11-16T10:00:00+00:00",
                candleCount: 2,
                capturedAt: "2026-11-16T10:01:00+00:00",
                contentSha256,
                validation: { valid: true, count: 2 },
                metadata: { origin: "provider_fetch" },
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (url.includes("/forex/quote/")) {
          return new Response(
            JSON.stringify({ bid: 1.1, ask: 1.1001, spread_pips: 1 }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }

        return new Response(JSON.stringify({ detail: "Unhandled test request." }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <MarketDataPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Historical Data Quality")).toBeInTheDocument();
    expect(await screen.findByText("Causal Research Features")).toBeInTheDocument();
    expect(await screen.findByText("Feature set ready")).toBeInTheDocument();
    expect(await screen.findByText("RSI 14")).toBeInTheDocument();
    expect(await screen.findByText("EMA 50 / 200 Spread")).toBeInTheDocument();
    expect(screen.getByText(/not entry signals/i)).toBeInTheDocument();
    expect(await screen.findByText("Detected gaps")).toBeInTheDocument();
    expect(await screen.findByText("Saved Research Datasets")).toBeInTheDocument();
    expect(await screen.findByText(/SHA-256 a{16}/)).toBeInTheDocument();
    expect(screen.getByText(/preliminary diagnostics/i)).toBeInTheDocument();
  });
});
