import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketDataPage } from "./market-data-page";


describe("MarketDataPage", () => {
  it("renders the market chat thread after a question is submitted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/market-data/candles")) {
          return new Response(
            JSON.stringify([
              {
                time: "2026-04-05T00:00:00+00:00",
                open: 100,
                high: 103,
                low: 99,
                close: 102,
                volume: 1200,
              },
            ]),
            {
              status: 200,
              headers: { "Content-Type": "application/json" },
            },
          );
        }

        if (url.includes("/ai/chat") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              threadId: "thread-1",
              reply: "The market still looks constructive.",
              messages: [
                {
                  id: "m1",
                  role: "user",
                  content: "Give me a quick market read.",
                  createdAt: "2026-04-05T00:00:00+00:00",
                },
                {
                  id: "m2",
                  role: "assistant",
                  content: "The market still looks constructive.",
                  createdAt: "2026-04-05T00:00:01+00:00",
                },
              ],
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
        <MarketDataPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("button", { name: /Zoom In/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Zoom Out/i })).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: /Ask About This Market/i }));

    expect(await screen.findByText(/The market still looks constructive\./i)).toBeInTheDocument();
    expect(screen.getByText(/^Research Assistant$/i)).toBeInTheDocument();
  });
});
