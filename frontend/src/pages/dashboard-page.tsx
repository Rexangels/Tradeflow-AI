import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { MetricCard } from "../components/ui/metric-card";
import { useWorkspaceStore } from "../stores/workspace-store";

export function DashboardPage() {
  const { symbol, timeframe } = useWorkspaceStore();
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
  });
  const [message, setMessage] = useState(`Give me a quick read on ${symbol} and whether the trend template still looks healthy on ${timeframe}.`);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);

  useEffect(() => {
    setThreadId(undefined);
    setMessage(`Give me a quick read on ${symbol} and whether the trend template still looks healthy on ${timeframe}.`);
  }, [symbol, timeframe]);

  const chatMutation = useMutation({
    mutationFn: () => api.chat({ message, symbol, timeframe, threadId }),
    onSuccess: (payload) => {
      setThreadId(payload.threadId);
    },
  });
  const chatError = chatMutation.error ? (chatMutation.error as Error).message : null;

  const monthlyUsage = settingsQuery.data?.monthlyUsage;
  const dashboard = settingsQuery.data?.dashboard as
    | {
        latestBacktests?: Array<{ id: string; symbol: string; metrics: { totalReturnPct: number; sharpeRatio: number } }>;
        watchlist?: Array<{ symbol: string; lastPrice: number; changePct: number }>;
      }
    | undefined;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Backtests This Month" value={String(monthlyUsage?.backtests ?? 0)} />
        <MetricCard label="AI Messages" value={String(monthlyUsage?.aiMessages ?? 0)} />
        <MetricCard label="Live Trading" value={settingsQuery.data?.liveTradingStatus === "coming_soon" ? "Coming Soon" : "Active"} tone="warning" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Latest Runs</p>
              <h3 className="mt-2 text-2xl font-semibold">Recent backtests</h3>
            </div>
          </div>
          <div className="mt-5 space-y-3">
            {(dashboard?.latestBacktests ?? []).map((backtest) => (
              <div key={backtest.id} className="rounded-3xl border border-slate-800 bg-slate-900/60 p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium">{backtest.symbol}</p>
                    <p className="text-sm text-slate-400">Sharpe {backtest.metrics.sharpeRatio.toFixed(2)}</p>
                  </div>
                  <span className="text-lg font-semibold text-emerald-300">{backtest.metrics.totalReturnPct.toFixed(2)}%</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Research Assistant</p>
          <h3 className="mt-2 text-2xl font-semibold">Operator conversation</h3>
          <textarea
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            className="mt-5 min-h-32 w-full rounded-3xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none"
          />
          <button
            type="button"
            onClick={() => chatMutation.mutate()}
            className="mt-4 rounded-2xl bg-cyan-300 px-4 py-3 font-semibold text-slate-950"
          >
            {chatMutation.isPending ? "Thinking..." : "Ask TradeFlow AI"}
          </button>
          {chatError ? (
            <div className="mt-4 rounded-3xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">{chatError}</div>
          ) : null}
          <div className="mt-4 space-y-3">
            {(chatMutation.data?.messages ?? []).length > 0 ? (
              chatMutation.data?.messages.map((entry) => (
                <div key={entry.id} className="rounded-3xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-200">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{entry.role}</p>
                  <p className="mt-2 whitespace-pre-wrap">{entry.content}</p>
                </div>
              ))
            ) : (
              <div className="rounded-3xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-200">
                Ask for a market read, a strategy critique, or a summary of recent research activity.
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Watchlist</p>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          {(dashboard?.watchlist ?? []).map((item) => (
            <div key={item.symbol} className="rounded-3xl border border-slate-800 bg-slate-900/60 p-4">
              <p className="text-sm text-slate-400">{item.symbol}</p>
              <p className="mt-2 text-2xl font-semibold">${item.lastPrice.toFixed(2)}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
