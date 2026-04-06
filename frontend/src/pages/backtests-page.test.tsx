import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useWorkspaceStore } from "../stores/workspace-store";
import { BacktestsPage } from "./backtests-page";


describe("BacktestsPage", () => {
  it("renders replay controls and plain-language interpretation after a run", async () => {
    useWorkspaceStore.setState({
      symbol: "ETHUSDT",
      timeframe: "1h",
      selectedAgent: null,
      latestBacktest: null,
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes("/agents")) {
          return new Response(
            JSON.stringify([
              {
                id: "agent-1",
                name: "Trend Research Template",
                type: "template",
                rewardStyle: "balanced",
                riskTolerance: 0.4,
                holdingBehavior: "short-term",
                strategies: [
                  {
                    id: "trend-following",
                    name: "Trend Following",
                    description: "EMA crossover entries with momentum-aware exits.",
                    enabled: true,
                  },
                ],
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }

        if (url.includes("/market-data/candles")) {
          const candles = Array.from({ length: 500 }, (_, index) => ({
            time: new Date(Date.UTC(2026, 3, 1, index)).toISOString(),
            open: 100 + index,
            high: 102 + index,
            low: 99 + index,
            close: 101 + index,
            volume: 1000 + index,
          }));
          return new Response(JSON.stringify(candles), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }

        if (url.includes("/backtests") && init?.method === "POST") {
          return new Response(
            JSON.stringify({
              id: "backtest-1",
              symbol: "ETHUSDT",
              timeframe: "1h",
              agent: {
                id: "agent-1",
                name: "Trend Research Template",
                type: "template",
                rewardStyle: "balanced",
                riskTolerance: 0.4,
                holdingBehavior: "short-term",
                strategies: [
                  {
                    id: "trend-following",
                    name: "Trend Following",
                    description: "EMA crossover entries with momentum-aware exits.",
                    enabled: true,
                  },
                ],
              },
              settings: {
                startingBalance: 10000,
                feeRate: 0.001,
                slippageRate: 0.0005,
                positionSizeFraction: 0.95,
              },
              metrics: {
                totalReturnPct: 2.4,
                totalProfit: 240,
                maxDrawdownPct: 1.31,
                sharpeRatio: 5.67,
                winRate: 75,
                totalTrades: 4,
                endingBalance: 10240,
                benchmarkReturnPct: 74.43,
                benchmarkEndingBalance: 17442.81,
                excessReturnPct: -72.03,
                profitFactor: 2.35,
                expectancy: 15,
                exposureTimePct: 6.6,
              },
              validation: {
                candlesChecked: 500,
                isSorted: true,
                warnings: [],
              },
              walkForward: {
                available: true,
                verdict: "mixed",
                trainCandlesPerWindow: 250,
                testCandlesPerWindow: 100,
                windowCount: 3,
                benchmarkBeatRatePct: 33.33,
                profitableWindowPct: 66.67,
                averageTestReturnPct: 4.2,
                averageTestBenchmarkReturnPct: 11.8,
                averageTestExcessReturnPct: -7.6,
                averageTestSharpeRatio: 1.9,
                averageTestDrawdownPct: 3.1,
                warnings: [],
                windows: [
                  {
                    index: 1,
                    trainStart: new Date(Date.UTC(2026, 3, 1, 0)).toISOString(),
                    trainEnd: new Date(Date.UTC(2026, 3, 10, 0)).toISOString(),
                    testStart: new Date(Date.UTC(2026, 3, 10, 1)).toISOString(),
                    testEnd: new Date(Date.UTC(2026, 3, 14, 0)).toISOString(),
                    trainReturnPct: 12.4,
                    trainBenchmarkReturnPct: 14.1,
                    testReturnPct: 4.5,
                    testBenchmarkReturnPct: 9.8,
                    testExcessReturnPct: -5.3,
                    testSharpeRatio: 1.8,
                    testMaxDrawdownPct: 2.7,
                    testTotalTrades: 3,
                  },
                ],
              },
              modelAnalysis: {
                available: true,
                modelType: "baseline_logistic_regression",
                labelHorizonBars: 6,
                trainSamples: 240,
                testSamples: 100,
                featuresUsed: ["EMA spread", "RSI position", "Bollinger position"],
                performance: {
                  trainAccuracyPct: 61.2,
                  testAccuracyPct: 57.4,
                  testPrecisionPct: 58.9,
                  testRecallPct: 54.1,
                  testAverageForwardReturnPct: 1.7,
                  predictedLongHitRatePct: 60.3,
                },
                signal: {
                  asOf: new Date(Date.UTC(2026, 3, 5, 10)).toISOString(),
                  action: "buy",
                  confidencePct: 18.6,
                  probabilityUpPct: 68.6,
                  probabilityDownPct: 31.4,
                },
                topFeatures: [
                  {
                    name: "ema_spread",
                    label: "EMA spread",
                    value: 0.0123,
                    contribution: 0.3184,
                    effect: "supports_upside",
                    detail: "Fast EMA is above slow EMA, which supports upside continuation.",
                  },
                ],
                explanation: {
                  summary: "The baseline model sees a 68.60% probability of positive forward returns and currently leans BUY.",
                  reasoning: [
                    "Fast EMA is above slow EMA, which supports upside continuation.",
                    "RSI is above neutral, showing positive momentum pressure.",
                  ],
                  caveats: ["Held-out accuracy is still weak, so treat the signal as exploratory rather than production-ready."],
                  asOf: new Date(Date.UTC(2026, 3, 5, 10)).toISOString(),
                },
                tuning: {
                  enabled: true,
                  adaptationMode: "scheduled_retrain",
                  objective: "validation_quality_score",
                  candidateCount: 8,
                  trainSamples: 140,
                  validationSamples: 40,
                  testSamples: 60,
                  selectedConfig: {
                    horizonBars: 6,
                    learningRate: 0.2,
                    regularization: 0.0005,
                    buyThreshold: 0.56,
                    sellThreshold: 0.44,
                    epochs: 220,
                  },
                  bestValidationScore: 61.4,
                  validationPerformance: {
                    accuracyPct: 58.2,
                    precisionPct: 60.1,
                    recallPct: 55.4,
                    predictedLongHitRatePct: 62.8,
                    predictedLongCount: 11,
                    averageForwardReturnPct: 1.9,
                  },
                  topTrials: [
                    {
                      validationScore: 61.4,
                      horizonBars: 6,
                      learningRate: 0.2,
                      regularization: 0.0005,
                      buyThreshold: 0.56,
                      sellThreshold: 0.44,
                      accuracyPct: 58.2,
                      precisionPct: 60.1,
                      recallPct: 55.4,
                      predictedLongHitRatePct: 62.8,
                      predictedLongCount: 11,
                      averageForwardReturnPct: 1.9,
                    },
                  ],
                },
              },
              equityCurve: [],
              trades: [
                {
                  id: "trade-1",
                  type: "buy",
                  price: 200,
                  time: new Date(Date.UTC(2026, 3, 1, 3)).toISOString(),
                  quantity: 1,
                  notional: 200,
                  feePaid: 0.2,
                  reason: "Strategy entry signal confirmed.",
                },
              ],
              createdAt: new Date(Date.UTC(2026, 3, 5)).toISOString(),
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }

        if (url.includes("/ai/chat") && init?.method === "POST") {
          const payload = JSON.parse(String(init.body ?? "{}")) as {
            message?: string;
            tradeId?: string;
            replayTime?: string;
            playbackIndex?: number;
          };
          const isReplayFocus = Boolean(payload.replayTime);
          return new Response(
            JSON.stringify({
              threadId: "backtest-thread-1",
              reply: isReplayFocus
                ? "At this replay moment, the strategy had already revealed one trade and was waiting for the next qualified setup."
                : "This strategy is weak overall because it badly underperformed buy-and-hold and failed walk-forward validation.",
              messages: [
                {
                  id: "message-1",
                  role: "user",
                  content: payload.message ?? "Give me an operator brief for this run: verdict, why it happened, and the next tests worth running.",
                  createdAt: new Date(Date.UTC(2026, 3, 5, 10)).toISOString(),
                },
                {
                  id: "message-2",
                  role: "assistant",
                  content: isReplayFocus
                    ? "At this replay moment, the strategy had already revealed one trade and was waiting for the next qualified setup."
                    : "This strategy is weak overall because it badly underperformed buy-and-hold and failed walk-forward validation.",
                  createdAt: new Date(Date.UTC(2026, 3, 5, 10, 1)).toISOString(),
                },
              ],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
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
        <BacktestsPage />
      </QueryClientProvider>,
    );

    const [agentSelect] = await screen.findAllByRole("combobox");
    fireEvent.change(agentSelect!, {
      target: { value: "agent-1" },
    });
    fireEvent.click(await screen.findByRole("button", { name: /Run backtest/i }));

    expect(await screen.findByText(/lagged buy-and-hold by 72.03 percentage points/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Play Replay/i })).toBeInTheDocument();
    expect(screen.getByText(/Replay bar/i)).toBeInTheDocument();
    expect(screen.getByText(/Walk-Forward Validation/i)).toBeInTheDocument();
    expect(screen.getByText(/Active Signal Stack/i)).toBeInTheDocument();
    expect(screen.getByText(/Model Intelligence/i)).toBeInTheDocument();
    expect(screen.getByText(/The baseline model sees a 68.60% probability/i)).toBeInTheDocument();
    expect(screen.getByText(/Tuned Configuration/i)).toBeInTheDocument();
    expect(screen.getByText(/Top Tuning Trials/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Generate Brief/i }));
    expect(await screen.findByText(/This strategy is weak overall because it badly underperformed buy-and-hold/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Explain Current Replay Moment/i }));
    expect(await screen.findByText(/At this replay moment, the strategy had already revealed one trade/i)).toBeInTheDocument();
  }, 10000);
});
