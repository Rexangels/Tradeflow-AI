import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { CandlestickChart } from "../components/CandlestickChart";
import { api } from "../lib/api";
import { useWorkspaceStore } from "../stores/workspace-store";

export function MarketDataPage() {
  const { symbol, timeframe } = useWorkspaceStore();
  const [message, setMessage] = useState(`Give me a quick market read for ${symbol} on ${timeframe}.`);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);

  useEffect(() => {
    setThreadId(undefined);
    setMessage(`Give me a quick market read for ${symbol} on ${timeframe}.`);
  }, [symbol, timeframe]);

  const candlesQuery = useQuery({
    queryKey: ["candles", symbol, timeframe, "market-page"],
    queryFn: () => api.getCandles(symbol, timeframe, 120),
  });

  const chatMutation = useMutation({
    mutationFn: () => api.chat({ message, symbol, timeframe, threadId }),
    onSuccess: (payload) => {
      setThreadId(payload.threadId);
    },
  });

  const candleError = candlesQuery.error ? (candlesQuery.error as Error).message : null;
  const chatError = chatMutation.error ? (chatMutation.error as Error).message : null;

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Market Research</p>
        <h3 className="mt-2 text-2xl font-semibold">{symbol} · {timeframe}</h3>
        <p className="mt-3 max-w-2xl text-sm text-slate-400">
          Review the active market, inspect the latest candle structure, and ask the assistant for a market read on the current symbol and timeframe.
        </p>
      </section>

      {candleError ? (
        <section className="rounded-[2rem] border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-100">
          {candleError}
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-6">
          <CandlestickChart data={candlesQuery.data ?? []} />

          <section className="overflow-hidden rounded-[2rem] border border-slate-800 bg-slate-950/80">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-900/70 text-slate-400">
                <tr>
                  <th className="px-4 py-3">Time</th>
                  <th className="px-4 py-3">Open</th>
                  <th className="px-4 py-3">High</th>
                  <th className="px-4 py-3">Low</th>
                  <th className="px-4 py-3">Close</th>
                </tr>
              </thead>
              <tbody>
                {(candlesQuery.data ?? []).slice(-12).reverse().map((candle) => (
                  <tr key={candle.time} className="border-t border-slate-800">
                    <td className="px-4 py-3 text-slate-400">{new Date(candle.time).toLocaleString()}</td>
                    <td className="px-4 py-3">${candle.open.toFixed(2)}</td>
                    <td className="px-4 py-3 text-emerald-300">${candle.high.toFixed(2)}</td>
                    <td className="px-4 py-3 text-rose-300">${candle.low.toFixed(2)}</td>
                    <td className="px-4 py-3">${candle.close.toFixed(2)}</td>
                  </tr>
                ))}
                {!candlesQuery.isLoading && (candlesQuery.data ?? []).length === 0 ? (
                  <tr>
                    <td className="px-4 py-6 text-slate-500" colSpan={5}>
                      No candle data is available yet for this symbol and timeframe.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </section>
        </div>

        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Research Assistant</p>
          <h3 className="mt-2 text-2xl font-semibold">Market conversation</h3>
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
            {chatMutation.isPending ? "Thinking..." : "Ask About This Market"}
          </button>
          {chatError ? (
            <div className="mt-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
              {chatError}
            </div>
          ) : null}
          <div className="mt-4 space-y-3">
            {(chatMutation.data?.messages ?? []).length > 0 ? (
              chatMutation.data?.messages.map((entry) => (
                <div key={entry.id} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{entry.role}</p>
                  <p className="mt-2 whitespace-pre-wrap text-slate-200">{entry.content}</p>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
                Ask for a market read, a quick strategy critique, or a summary of how the active symbol is behaving.
              </div>
            )}
          </div>
        </section>
      </section>
    </div>
  );
}
