import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { queryClient } from "../../lib/query-client";
import type { TradeLogItem } from "../../shared";

const LESSONS = ["", "good-win", "good-loss", "chased", "early-m15", "news-slip", "spread-wide", "sized-big", "no-setup"];

function digest(rows: TradeLogItem[]) {
  const wins = rows.filter((t) => (t.realized_pnl ?? 0) > 0);
  const grossW = wins.reduce((a, t) => a + (t.realized_pnl ?? 0), 0);
  const grossL = Math.abs(rows.filter((t) => (t.realized_pnl ?? 0) <= 0).reduce((a, t) => a + (t.realized_pnl ?? 0), 0));
  return {
    n: rows.length,
    winPct: rows.length ? (wins.length / rows.length) * 100 : 0,
    pf: grossL > 0 ? grossW / grossL : grossW > 0 ? 99 : 0,
    exp: rows.length ? rows.reduce((a, t) => a + (t.realized_pnl ?? 0), 0) / rows.length : 0,
  };
}

export function TradeJournalTable() {
  const tradesQuery = useQuery({
    queryKey: ["trading-orders"],
    queryFn: () => api.getTradingOrders(100),
    refetchInterval: 10000,
  });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const reviewMutation = useMutation({
    mutationFn: (p: { id: string; followed_plan?: boolean | null; lesson_tag?: string; human_note?: string }) =>
      api.reviewJournalTrade(p.id, { followed_plan: p.followed_plan, lesson_tag: p.lesson_tag, human_note: p.human_note }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["trading-orders"] }),
  });

  const trades = tradesQuery.data ?? [];
  const closedTrades = trades.filter((t) => t.status === "closed" && t.realized_pnl !== null);
  const winningTrades = closedTrades.filter((t) => (t.realized_pnl ?? 0) > 0);
  const winRate = closedTrades.length > 0 ? (winningTrades.length / closedTrades.length) * 100 : 0;
  const totalRealizedPnl = closedTrades.reduce((acc, t) => acc + (t.realized_pnl ?? 0), 0);
  const byModule = new Map<string, TradeLogItem[]>();
  closedTrades.forEach((t) => {
    const k = t.strategy_version || "unknown";
    byModule.set(k, [...(byModule.get(k) ?? []), t]);
  });

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

      {byModule.size > 0 && (
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {[...byModule.entries()].map(([mod, rows]) => {
            const d = digest(rows);
            return (
              <div key={mod} className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2 text-[11px] text-slate-300">
                <p className="font-semibold text-slate-100 truncate" title={mod}>{mod}</p>
                <p className="mt-1 font-mono">
                  n={d.n} · win {d.winPct.toFixed(0)}% · PF {d.pf.toFixed(2)} · exp ${d.exp.toFixed(2)}
                </p>
                <p className="text-slate-500">Promote only at n≥30 with PF&gt;1.2 after costs.</p>
              </div>
            );
          })}
        </div>
      )}

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
              <th className="px-4 py-3 font-medium">Regime / Exit</th>
              <th className="px-4 py-3 font-medium text-right">MFE/MAE (R)</th>
              <th className="px-4 py-3 font-medium">Review</th>
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
                  <td className="px-4 py-3 text-slate-400 whitespace-nowrap">
                    {[t.regime, t.exit_reason].filter(Boolean).join(" · ") || "—"}
                    {t.session ? <span className="text-slate-500"> · {t.session}</span> : null}
                  </td>
                  <td className="px-4 py-3 font-mono text-right text-slate-300">
                    {t.mfe_r != null || t.mae_r != null ? `${t.mfe_r ?? "—"} / ${t.mae_r ?? "—"}` : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-400 min-w-52">
                    {t.status === "closed" ? (
                      <div className="flex flex-col gap-1.5">
                        <div className="flex items-center gap-1.5">
                          <select
                            className="rounded bg-slate-900 border border-slate-800 px-1.5 py-1 text-[11px]"
                            defaultValue={t.lesson_tag || ""}
                            onChange={(e) => reviewMutation.mutate({ id: t.id, lesson_tag: e.target.value })}
                            title="One lesson tag"
                          >
                            {LESSONS.map((l) => (
                              <option key={l} value={l}>{l || "lesson…"}</option>
                            ))}
                          </select>
                          <button
                            type="button"
                            className={`rounded px-1.5 py-1 text-[11px] border ${t.followed_plan ? "border-emerald-500/40 text-emerald-300" : "border-slate-800 text-slate-400"}`}
                            onClick={() => reviewMutation.mutate({ id: t.id, followed_plan: !(t.followed_plan ?? false) })}
                            title="Did you follow the plan?"
                          >
                            {t.followed_plan ? "plan ✓" : "plan?"}
                          </button>
                        </div>
                        <input
                          className="rounded bg-slate-900 border border-slate-800 px-1.5 py-1 text-[11px] w-full"
                          placeholder="140-char note…"
                          defaultValue={t.human_note || ""}
                          maxLength={140}
                          onChange={(e) => setNotes((n) => ({ ...n, [t.id]: e.target.value }))}
                          onBlur={(e) => {
                            if ((notes[t.id] ?? e.target.value) !== (t.human_note || "")) {
                              reviewMutation.mutate({ id: t.id, human_note: e.target.value });
                            }
                          }}
                        />
                      </div>
                    ) : (
                      <span className="text-slate-500">open — review at close</span>
                    )}
                  </td>
                </tr>
              );
            })}

            {!tradesQuery.isLoading && trades.length === 0 && (
              <tr>
                <td colSpan={11} className="px-4 py-8 text-center text-slate-500">
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
