import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PaperTradingPage } from "./paper-trading-page";


describe("PaperTradingPage", () => {
  it("surfaces risk-policy rejection messages from the API", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/paper-trading/account")) {
          return new Response(
            JSON.stringify({
              id: "account-1",
              cashBalance: 10000,
              equity: 10000,
              realizedPnl: 0,
              updatedAt: "2026-04-04T12:00:00+00:00",
              positions: [],
              recentOrders: [],
              riskPolicy: {
                tradingEnabled: true,
                maxOrderNotional: 2500,
                maxOpenPositions: 3,
                maxDailyLoss: 500,
                currentOpenPositions: 0,
                dailyRealizedLoss: 0,
              },
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          );
        }

        if (url.includes("/paper-trading/orders") && init?.method === "POST") {
          return new Response(JSON.stringify({ detail: "Order rejected by risk policy: max order notional is $2500.00." }), {
            status: 400,
            headers: { "Content-Type": "application/json" },
          });
        }

        return new Response(JSON.stringify({ detail: "Unhandled test request." }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={client}>
        <PaperTradingPage />
      </QueryClientProvider>,
    );

    const notionalInput = await screen.findByLabelText(/Notional/i);
    fireEvent.change(notionalInput, { target: { value: "3000" } });
    fireEvent.click(screen.getByRole("button", { name: /Execute paper order/i }));

    expect(await screen.findByText(/max order notional is \$2500\.00/i)).toBeInTheDocument();
  });

  it("explains what changed after a successful paper buy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/paper-trading/account")) {
          return new Response(
            JSON.stringify({
              id: "account-1",
              cashBalance: 10000,
              equity: 10000,
              realizedPnl: 0,
              updatedAt: "2026-04-04T12:00:00+00:00",
              positions: [],
              recentOrders: [],
              riskPolicy: {
                tradingEnabled: true,
                maxOrderNotional: 2500,
                maxOpenPositions: 3,
                maxDailyLoss: 500,
                currentOpenPositions: 0,
                dailyRealizedLoss: 0,
              },
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          );
        }

        if (url.includes("/paper-trading/orders") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              sessionId: "session-1",
              order: {
                id: "order-1",
                symbol: "ETHUSDT",
                side: "buy",
                quantity: 1.277568,
                fillPrice: 195.68,
                notional: 250,
                feePaid: 0.25,
                realizedPnl: 0,
                status: "filled",
                createdAt: "2026-04-04T12:01:00+00:00",
              },
              account: {
                id: "account-1",
                cashBalance: 9749.75,
                equity: 9999.75,
                realizedPnl: 0,
                updatedAt: "2026-04-04T12:01:00+00:00",
                positions: [
                  {
                    id: "position-1",
                    symbol: "ETHUSDT",
                    quantity: 1.277568,
                    averageEntryPrice: 195.68,
                    marketPrice: 195.68,
                    marketValue: 250,
                    unrealizedPnl: 0,
                    updatedAt: "2026-04-04T12:01:00+00:00",
                  },
                ],
                recentOrders: [
                  {
                    id: "order-1",
                    symbol: "ETHUSDT",
                    side: "buy",
                    quantity: 1.277568,
                    fillPrice: 195.68,
                    notional: 250,
                    feePaid: 0.25,
                    realizedPnl: 0,
                    status: "filled",
                    createdAt: "2026-04-04T12:01:00+00:00",
                  },
                ],
                riskPolicy: {
                  tradingEnabled: true,
                  maxOrderNotional: 2500,
                  maxOpenPositions: 3,
                  maxDailyLoss: 500,
                  currentOpenPositions: 1,
                  dailyRealizedLoss: 0,
                },
              },
            }),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          );
        }

        return new Response(JSON.stringify({ detail: "Unhandled test request." }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    render(
      <QueryClientProvider client={client}>
        <PaperTradingPage />
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Execute paper order/i }));

    expect(await screen.findByText(/Paper buy executed for ETHUSDT/i)).toBeInTheDocument();
    expect(screen.getByText(/Cash moved by -\$250.25/i)).toBeInTheDocument();
    expect(screen.getByText(/Realized P&L stays unchanged until you sell/i)).toBeInTheDocument();
  });
});
