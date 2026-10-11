import { useMutation, useQuery } from "@tanstack/react-query";
import { Send, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { CandlestickChart } from "../components/CandlestickChart";
import { OrderFormPanel } from "../components/trading/OrderFormPanel";
import { api } from "../lib/api";
import { useWorkspaceStore } from "../stores/workspace-store";

export function MarketDataPage() {
  const { symbol, timeframe } = useWorkspaceStore();
  const [message, setMessage] = useState(`Give me a technical breakdown for ${symbol} on ${timeframe} with indicators and key levels.`);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);

  useEffect(() => {
    setThreadId(undefined);
    setMessage(`Give me a technical breakdown for ${symbol} on ${timeframe} with indicators and key levels.`);
  }, [symbol, timeframe]);

  // Queries
  const candlesQuery = useQuery({
    queryKey: ["candles", symbol, timeframe, "market-page"],
    queryFn: () => api.getCandles(symbol, timeframe, 120),
  });

  const quoteQuery = useQuery({
    queryKey: ["forex-quote", symbol],
    queryFn: () => api.getForexQuote(symbol),
    refetchInterval: 5000,
  });

  const marketStatusQuery = useQuery({
    queryKey: ["market-data-status", symbol, timeframe],
    queryFn: () => api.getMarketDataStatus(symbol, timeframe),
    refetchInterval: 60_000,
  });

  const chatMutation = useMutation({
    mutationFn: () => api.chat({ message, symbol, timeframe, threadId }),
    onSuccess: (payload) => {
      setThreadId(payload.threadId);
      setMessage("");
    },
  });

  const isJpy = symbol.includes("JPY");
  const decimals = isJpy ? 3 : 5;
  const quote = quoteQuery.data;
  const candles = candlesQuery.data ?? [];
  const candleError = candlesQuery.error ? (candlesQuery.error as Error).message : null;
  const status = marketStatusQuery.data;
  const candleSource = status?.source ?? candles[0]?.source ?? "unknown";
  const isSynthetic = candleSource === "synthetic_demo";
  const sourceLabel = candleSource === "synthetic_demo"
    ? "Synthetic demo data"
    : candleSource === "mt5"
      ? "MetaTrader 5"
      : candleSource === "alpaca"
        ? "Alpaca market data"
        : "Source not verified";

  return (
    <div className="space-y-6">
      {/* Pair Header with Live Quote */}
      <section className="rounded-3xl border border-slate-800/80 bg-gradient-to-r from-slate-950 via-slate-900/60 to-slate-950 p-6 backdrop-blur shadow-lg shadow-black/20">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
              <p className={`text-xs font-bold uppercase tracking-[0.24em] ${isSynthetic ? "text-amber-400" : "text-cyan-400"}`}>
                {sourceLabel}
              </p>
            </div>
            <h2 className="mt-1 text-2xl font-bold text-slate-100">
              {symbol} · {timeframe} Timeframe
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              Real-time candlestick charts, indicator confluence, and direct execution desk.
            </p>
            {status && (
              <p className={`mt-2 text-[11px] ${status.isRealData ? "text-emerald-300" : "text-amber-300"}`}>
                {status.isRealData
                  ? `Verified ${sourceLabel} · latest bar ${status.latestBarTime ? new Date(status.latestBarTime).toLocaleString() : "available"}`
                  : `Data verification: ${status.error ?? "not connected to a real provider"}`}
              </p>
            )}
          </div>

          {quote && (
            <div className="flex flex-wrap items-center gap-3">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/80 px-4 py-2 text-center">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-medium">BID</span>
                <span className="font-mono text-base font-bold text-rose-400">{quote.bid.toFixed(decimals)}</span>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/80 px-4 py-2 text-center">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-medium">ASK</span>
                <span className="font-mono text-base font-bold text-emerald-400">{quote.ask.toFixed(decimals)}</span>
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/80 px-4 py-2 text-center">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 block font-medium">SPREAD</span>
                <span className="font-mono text-sm font-bold text-cyan-300">{quote.spread_pips.toFixed(1)} pips</span>
              </div>
            </div>
          )}
        </div>
      </section>

      {candleError && (
        <section className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-200">
          {candleError}
        </section>
      )}

      {isSynthetic && (
        <section className="rounded-2xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-100">
          <span className="font-semibold">Demo data only.</span> These candles are generated for interface testing and cannot be used for strategy validation or order execution. Connect MT5 or Alpaca for real market data.
        </section>
      )}

      {!candleError && candles.length > 0 && candleSource === "unknown" && (
        <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4 text-xs text-slate-300">
          Candle provenance is unavailable. Treat analysis as exploratory until the feed is refreshed from a verified provider.
        </section>
      )}

      {/* Main Chart and Side Order Panel */}
      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <div className="space-y-6">
          {/* Candlestick Chart */}
          <div className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
            <CandlestickChart data={candles} />
          </div>

          {/* Candle Data Feed Table with Forex Decimal Precision */}
          <section className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950/70 backdrop-blur">
            <div className="border-b border-slate-800/80 px-5 py-3.5 flex items-center justify-between">
              <h3 className="font-semibold text-slate-100 text-sm">Recent Candlestick Bars</h3>
              <span className="text-xs text-slate-400 font-mono">{candles.length} Bars · {sourceLabel}</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-900/60 uppercase tracking-wider text-slate-400 border-b border-slate-800/60">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Time (UTC)</th>
                    <th className="px-4 py-2.5 font-medium text-right">Open</th>
                    <th className="px-4 py-2.5 font-medium text-right">High</th>
                    <th className="px-4 py-2.5 font-medium text-right">Low</th>
                    <th className="px-4 py-2.5 font-medium text-right">Close</th>
                    <th className="px-4 py-2.5 font-medium text-right">Volume</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50 font-mono">
                  {candles.slice(-10).reverse().map((candle) => {
                    const isUp = candle.close >= candle.open;
                    return (
                      <tr key={candle.time} className="hover:bg-slate-900/40 transition-colors">
                        <td className="px-4 py-2.5 text-slate-400 font-sans">
                          {new Date(candle.time).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-300">{candle.open.toFixed(decimals)}</td>
                        <td className="px-4 py-2.5 text-right text-emerald-400">{candle.high.toFixed(decimals)}</td>
                        <td className="px-4 py-2.5 text-right text-rose-400">{candle.low.toFixed(decimals)}</td>
                        <td className={`px-4 py-2.5 text-right font-bold ${isUp ? "text-emerald-400" : "text-rose-400"}`}>
                          {candle.close.toFixed(decimals)}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-400">{candle.volume.toLocaleString()}</td>
                      </tr>
                    );
                  })}
                  {!candlesQuery.isLoading && candles.length === 0 && (
                    <tr>
                      <td className="px-4 py-6 text-center text-slate-500 font-sans" colSpan={6}>
                        No candle data returned for this pair.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        {/* Right Column: Order Form & AI Chat */}
        <div className="space-y-6">
          <OrderFormPanel initialSymbol={symbol} />

          {/* AI Market Conversation */}
          <section className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-cyan-400" />
                  <h3 className="font-semibold text-slate-100 text-sm">Market Intelligence</h3>
                </div>
                <span className="text-[10px] text-cyan-400 bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 rounded-md font-semibold">
                  {symbol}
                </span>
              </div>

              <div className="mt-3.5 space-y-2.5 max-h-72 overflow-y-auto pr-1">
                {(chatMutation.data?.messages ?? []).length > 0 ? (
                  chatMutation.data?.messages.map((entry) => (
                    <div
                      key={entry.id}
                      className={`rounded-xl p-3 text-xs leading-relaxed ${
                        entry.role === "user"
                          ? "bg-cyan-950/40 border border-cyan-800/40 text-cyan-100 ml-4"
                          : entry.role === "tool"
                          ? "bg-slate-900/40 border border-slate-800/60 text-slate-400 text-[11px]"
                          : "bg-slate-900/80 border border-slate-800 text-slate-200 mr-2"
                      }`}
                    >
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">
                        {entry.role === "user" ? "You" : entry.role === "tool" ? "Alpaca Context" : "TradeFlow AI"}
                      </p>
                      <p className="whitespace-pre-wrap">{entry.content}</p>
                    </div>
                  ))
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-800/80 p-4 text-xs text-slate-400 text-center">
                    Ask for a technical confluence read on {symbol}, key support/resistance levels, or risk limits.
                  </div>
                )}
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800/60">
              <div className="relative flex items-center">
                <input
                  type="text"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      chatMutation.mutate();
                    }
                  }}
                  placeholder={`Ask about ${symbol} setup...`}
                  className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3.5 py-2.5 pr-10 text-xs text-slate-100 outline-none focus:border-cyan-500"
                />
                <button
                  type="button"
                  disabled={chatMutation.isPending || !message.trim()}
                  onClick={() => chatMutation.mutate()}
                  className="absolute right-2 p-1.5 rounded-lg bg-cyan-500 text-slate-950 hover:bg-cyan-400 transition-colors disabled:opacity-40"
                >
                  <Send className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
