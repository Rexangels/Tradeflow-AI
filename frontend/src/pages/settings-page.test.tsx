import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./settings-page";


describe("SettingsPage", () => {
  it("renders system status and risk policy details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            planName: "Founding Operator",
            monthlyUsage: {
              backtests: 3,
              aiMessages: 1,
              paperOrders: 2,
            },
            liveTradingStatus: "coming_soon",
            systemStatus: {
              databaseEngine: "django.db.backends.sqlite3",
              sqliteMode: true,
              geminiConfigured: false,
              marketDataProviderUrl: "https://api.binance.us",
              marketDataFallbackMode: "synthetic",
              paperTradingEnabled: true,
              liveTradingEnabled: false,
            },
            riskPolicy: {
              tradingEnabled: true,
              maxOrderNotional: 2500,
              maxOpenPositions: 3,
              maxDailyLoss: 500,
              currentOpenPositions: 1,
              dailyRealizedLoss: 125,
            },
            dashboard: {},
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={client}>
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/Database engine: django\.db\.backends\.sqlite3/i)).toBeInTheDocument();
    expect(screen.getByText(/SQLite mode: Enabled for local proof-of-concept/i)).toBeInTheDocument();
    expect(screen.getByText(/Market data fallback: synthetic/i)).toBeInTheDocument();
    expect(screen.getByText(/Current daily realized loss: \$125\.00/i)).toBeInTheDocument();
  });
});
