import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PaperTradingPage } from "./paper-trading-page";


describe("PaperTradingPage", () => {
  it("renders the current broker execution, risk and journal workspaces without submitting an order", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      let payload: unknown = {};

      if (url.includes("/trading/account")) {
        payload = {
          mode: "paper",
          broker: "alpaca",
          brokerName: "Alpaca Paper",
          status: "ACTIVE",
          currency: "USD",
          equity: 25000,
          cash: 25000,
          buying_power: 100000,
          totalUnrealizedPnl: 0,
        };
      } else if (url.includes("/trading/positions")) {
        payload = [];
      } else if (url.includes("/risk/rules")) {
        payload = {
          max_risk_pct: 1,
          max_positions: 1,
          daily_loss_limit_pct: 2,
          min_rr_ratio: 1.5,
        };
      } else if (url.includes("/forex/quote/")) {
        payload = { symbol: "EURUSD", bid: 1.1, ask: 1.1001, mid: 1.10005, spread_pips: 1 };
      } else if (url.includes("/trading/benchmark")) {
        payload = null;
      } else if (url.includes("/trading/orders")) {
        payload = [];
      }

      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={client}>
        <PaperTradingPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Trade Execution")).toBeInTheDocument();
    expect(await screen.findByText("Server-Enforced Risk Guardrails")).toBeInTheDocument();
    expect(await screen.findByText("Trade Performance Benchmark")).toBeInTheDocument();
    expect(await screen.findByText("No open positions in Alpaca account.")).toBeInTheDocument();

    const submittedOrder = fetchMock.mock.calls.some(([input, init]) =>
      String(input).includes("/trading/orders") && init?.method === "POST",
    );
    expect(submittedOrder).toBe(false);
  });
});
