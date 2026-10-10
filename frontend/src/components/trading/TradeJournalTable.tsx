import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { api } from "../../lib/api";

export function TradeJournalTable() {
  const tradesQuery = useQuery({
    queryKey: ["trading-orders"],
    queryFn: () => api.getTradingOrders(100),
    refetchInterval: 10000,
  });

  const trades = tradesQuery.data ?? [];
  const closedTrades = trades.filter((t) => t.status === "closed" && t.realized_pnl !== null);
  const winningTrades = closedTrades.filter((t) => (t.realized_pnl ?? 0) > 0);
  const winRate = closedTrades.length > 0 ? (winningTrades.length / closedTrades.length) * 100 : 0;
  const totalRealizedPnl = closedTrades.reduce((acc, t) => acc + (t.realized_pnl ?? 0), 0);

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-slate-950/70 p-5 backdrop-blur">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-cyan-400" />
            <h3 className="font-semibold text-slate-100 text-base">Trade Audit Journal</h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Full historical audit of all orders, fill prices, and realized P&L
          </p>
        </div>

        <div className="flex items-center gap-4 text-xs">
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-1.5">
            <span className="text-slate-400">Win Rate: </span>
            <span className="font-semibold text-slate-100 font-mono">
              {winRate.toFixed(1)}% ({winningTrades.length}/{closedTrades.length})
            </span>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-1.5">
            <span className="text-slate-400">Total P&L: </span>
            <span
              className={`font-semibold font-mono ${
                totalRealizedPnl >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {totalRealizedPnl >= 0 ? "+" : ""}${totalRealizedPnl.toFixed(2)}
            </span>
          </div>
        </div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-900/60 uppercase tracking-wider text-slate-400 border-b border-slate-800/60">
            <tr>
              <th className="px-4 py-3 font-medium">Time</th>
              <th className="px-4 py-3 font-medium">Pair</th>
              <th className="px-4 py-3 font-medium">Side</th>
              <th className="px-4 py-3 font-medium text-right">Units</th>
              <th className="px-4 py-3 font-medium text-right">Entry</th>
              <th className="px-4 py-3 font-medium text-right">Exit</th>
              <th className="px-4 py-3 font-medium text-right">Realized P&L</th>
              <th className="px-4 py-3 font-medium text-center">Status</th>
              <th className="px-4 py-3 font-medium">Reasoning / Notes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {trades.map((t) => {
              const isJpy = t.symbol.includes("JPY");
              const decimals = isJpy ? 3 : 5;
              const hasPnl = t.realized_pnl !== null;
              const isProfit = (t.realized_pnl ?? 0) >= 0;

              return (
                <tr key={t.id} className="hover:bg-slate-900/40 transition-colors">
                  <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                    {new Date(t.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td className="px-4 py-3 font-semibold text-slate-100">{t.symbol}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                        t.side.toLowerCase() === "buy"
                          ? "bg-emerald-500/15 text-emerald-400"
                          : "bg-rose-500/15 text-rose-400"
                      }`}
                    >
                      {t.side.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-right text-slate-200">{t.qty.toLocaleString()}</td>
                  <td className="px-4 py-3 font-mono text-right text-slate-300">
                    {t.entry_price ? t.entry_price.toFixed(decimals) : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-right text-slate-300">
                    {t.exit_price ? t.exit_price.toFixed(decimals) : "—"}
                  </td>
                  <td className="px-4 py-3 font-mono text-right font-semibold">
                    {hasPnl ? (
                      <span className={isProfit ? "text-emerald-400" : "text-rose-400"}>
                        {isProfit ? "+" : ""}${t.realized_pnl?.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium uppercase ${
                        t.status === "open"
                          ? "bg-amber-500/15 text-amber-400 border border-amber-500/20"
                          : t.status === "closed"
                          ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/20"
                          : "bg-slate-700/30 text-slate-400"
                      }`}
                    >
                      {t.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 max-w-xs truncate" title={t.ai_reasoning}>
                    {t.ai_reasoning || "Direct operator execution"}
                  </td>
                </tr>
              );
            })}

            {!tradesQuery.isLoading && trades.length === 0 && (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                  No orders recorded in the trade log yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
