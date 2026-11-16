import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SettingsPage } from "./settings-page";


describe("SettingsPage", () => {
  it("renders broker gateway, currency watchlist and current risk settings", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
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
          };
        } else if (url.includes("/trading/broker")) {
          payload = {
            activeBroker: "alpaca",
            brokers: {
              alpaca: {
                name: "Alpaca Paper",
                mode: "paper",
                connected: true,
                equity: 25000,
                supportedAssets: ["stocks", "crypto"],
              },
              mt5: {
                name: "MetaTrader 5",
                login: "test-login",
                server: "test-server",
                currency: "USD",
                isCentAccount: true,
                balance: 25000,
                connected: false,
                supportedAssets: ["forex"],
              },
            },
          };
        } else if (url.includes("/forex/pairs")) {
          payload = [
            {
              id: "eurusd",
              symbol: "EURUSD",
              normalizedSymbol: "EURUSD",
              isWatched: true,
              defaultQty: 1000,
              notes: "Test fixture",
              quote: {
                symbol: "EURUSD",
                bid: 1.1,
                ask: 1.1001,
                mid: 1.10005,
                spread_pips: 1,
                timestamp: "2026-11-16T10:00:00+00:00",
              },
            },
          ];
        } else if (url.includes("/risk/rules")) {
          payload = {
            max_risk_pct: 1,
            max_positions: 1,
            daily_loss_limit_pct: 2,
            min_rr_ratio: 1.5,
          };
        }

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
        <SettingsPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Broker Router & Institutional Risk Controls")).toBeInTheDocument();
    expect(await screen.findByText("Active Execution Broker Gateway")).toBeInTheDocument();
    expect(await screen.findByText("Currency Watchlist Manager")).toBeInTheDocument();
    expect(await screen.findByText("EURUSD")).toBeInTheDocument();
    expect(screen.getByText("1 Active Pairs")).toBeInTheDocument();
    expect(await screen.findByText("Server-Enforced Risk Guardrails")).toBeInTheDocument();
  });
});
