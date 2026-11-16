import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AgentsPage } from "./agents-page";


describe("AgentsPage strategy registry", () => {
  it("loads strategy options and displays their research-only contract", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const payload = url.includes("/strategies/catalog")
          ? [
              {
                strategy_id: "trend-following",
                name: "Trend Following",
                version: "legacy-ema-cross/1.0",
                description: "Completed-bar EMA 9/21 crossover baseline.",
                engine: "legacy",
                required_features: ["ema9", "ema21"],
                eligible_regimes: ["UPTREND", "DOWNTREND"],
                minimum_bars: 30,
                regime_policy: "advisory_only",
                implementation_status: "experimental",
                execution_authority: "none",
                aliases: [],
              },
              {
                strategy_id: "mean-reversion",
                name: "Mean Reversion",
                version: "legacy-bollinger-rsi/1.0",
                description: "Bollinger-band and RSI mean-reversion baseline.",
                engine: "legacy",
                required_features: ["bollinger20", "rsi14"],
                eligible_regimes: ["RANGE"],
                minimum_bars: 30,
                regime_policy: "advisory_only",
                implementation_status: "experimental",
                execution_authority: "none",
                aliases: [],
              },
              {
                strategy_id: "trend-breakout-v1",
                name: "Trend Breakout",
                version: "trend-breakout-v1/1.0.0",
                description: "Multi-timeframe trend/breakout research engine with next-bar-open entries, ATR stops and targets.",
                engine: "trend_breakout_v1",
                required_features: ["atr14", "ema50", "ema200", "multi_timeframe_structure"],
                eligible_regimes: ["UPTREND", "DOWNTREND"],
                minimum_bars: 80,
                regime_policy: "strategy_internal",
                implementation_status: "experimental",
                execution_authority: "none",
                aliases: ["trend-breakout"],
              },
            ]
          : [];

        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <AgentsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Enabled strategies")).toBeInTheDocument();
    expect(await screen.findByText("Trend Breakout")).toBeInTheDocument();
    expect(await screen.findByText(/80 minimum bars/)).toBeInTheDocument();
    expect(screen.getByText(/no broker execution authority/i)).toBeInTheDocument();
    expect(screen.getByText(/strategy's internal regime rules/i)).toBeInTheDocument();
  });
});
