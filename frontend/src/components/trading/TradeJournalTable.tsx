import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpen, RefreshCw } from "lucide-react";
import { useState } from "react";
import { api, type TradeBenchmarkGroup } from "../../lib/api";
import { queryClient } from "../../lib/query-client";
import type { TradeLogItem } from "../../shared";

const LESSONS = ["", "good-win", "good-loss", "chased", "early-m15", "news-slip", "spread-wide", "sized-big", "no-setup"];

export function TradeJournalTable() {
  const benchmarkQuery = useQuery({
    queryKey: ["trade-benchmark"],
    queryFn: api.getTradeBenchmark,
    refetchInterval: 15000,
  });
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
  const syncMutation = useMutation({
    mutationFn: api.syncTradeBenchmark,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["trade-benchmark"] }),
        queryClient.invalidateQueries({ queryKey: ["trading-orders"] }),
      ]);
    },
  });

  const trades = tradesQuery.data ?? [];
  const benchmark = benchmarkQuery.data;
  const stats = benchmark?.summary;

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-slate-950/70 p-5 backdrop-blur">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-cyan-400" />
            <h3 className="font-semibold text-slate-100 text-base">Trade Performance Benchmark</h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            All-time closed-trade outcomes from the full journal, grouped by strategy and pair
          </p>
        </div>
        <button
          type="button"
          onClick={() => syncMutation.mutate()}
          disabled={syncMutation.isPending}
          className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-900 px-3 text-xs font-medium text-slate-200 hover:border-cyan-500/50 hover:text-cyan-200 disabled:cursor-wait disabled:opacity-60"
          aria-label="Sync MT5 trades closed outside the platform"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${syncMutation.isPending ? "animate-spin" : ""}`} />
          {syncMutation.isPending ? "Syncing MT5" : "Sync MT5 closes"}
        </button>
      </div>

      {syncMutation.data && <p className="mt-3 text-xs text-slate-400" role="status">{!syncMutation.data.connected ? "MT5 is not connected. Broker-side closes were not synchronized." : syncMutation.data.complete === false ? "MT5 connected, but open-position status could not be confirmed. No trades were changed; try again." : `${syncMutation.data.synced} externally closed MT5 trade${syncMutation.data.synced === 1 ? "" : "s"} reconciled from broker history.`}</p>}
      {syncMutation.isError && <p className="mt-3 text-xs text-rose-300" role="alert">MT5 trade sync failed. Check the terminal connection and try again.</p>}

      {benchmarkQuery.isError && <p role="alert" className="mt-4 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">Benchmark data could not be loaded. Refresh the page or check the backend connection.</p>}

      {stats && <>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <BenchmarkMetric label="Scored closed trades" value={`${stats.scoredCount}`} detail={`${stats.wins} wins · ${stats.losses} losses · ${stats.breakeven} breakeven`} />
          <BenchmarkMetric label="Win rate" value={stats.winRatePct == null ? "—" : `${stats.winRatePct.toFixed(1)}%`} detail="Closed trades with recorded P&L only" />
          <BenchmarkMetric label="P&L after recorded fees" value={formatMoney(stats.netPnlAfterRecordedFees)} detail={`Gross ${formatMoney(stats.grossPnl)} · fees recorded ${formatMoney(stats.recordedFees)}`} tone={stats.netPnlAfterRecordedFees >= 0 ? "positive" : "negative"} />
          <BenchmarkMetric label="Expectancy / trade" value={stats.expectancy == null ? "—" : formatMoney(stats.expectancy)} detail={`PF ${stats.profitFactor == null ? "—" : stats.profitFactor.toFixed(2)} · max drawdown ${formatMoney(stats.maxDrawdown)}`} tone={stats.expectancy == null ? "neutral" : stats.expectancy >= 0 ? "positive" : "negative"} />
        </div>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-2 text-[11px] text-slate-400">
          <span>Records: {stats.recordCount} total · {stats.openCount} open · {stats.unscoredClosedCount} closed without P&amp;L</span>
          <span>Fee coverage: {stats.feeCoveragePct == null ? "no scored trades" : `${stats.feeCoveragePct.toFixed(0)}% of scored trades`}</span>
          <span>Results describe recorded history; they do not establish future profitability.</span>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {benchmark?.byStrategy.length ? <BenchmarkBreakdown title="By strategy version" rows={benchmark.byStrategy} /> : null}
          {benchmark?.bySymbol.length ? <BenchmarkBreakdown title="By pair" rows={benchmark.bySymbol} /> : null}
        </div>
        {stats.scoredCount < 30 && <p className="mt-3 text-xs text-amber-300">Early evidence: fewer than 30 scored closed trades. Treat these results as preliminary.</p>}
      </>}
      {!benchmarkQuery.isLoading && stats?.recordCount === 0 && <p className="mt-4 rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-sm text-slate-400">No trades have been recorded yet. Trades will appear here after they are logged and closed.</p>}

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-slate-900/60 uppercase tracking-wider text-slate-400 border-b border-slate-800/60">
            <tr>
              <th className="px-4 py-3 font-medium">Entry time</th>
              <th className="px-4 py-3 font-medium">Pair</th>
              <th className="px-4 py-3 font-medium">Side</th>
              <th className="px-4 py-3 font-medium text-right">Units</th>
              <th className="px-4 py-3 font-medium text-right">Entry</th>
              <th className="px-4 py-3 font-medium text-right">Exit</th>
              <th className="px-4 py-3 font-medium text-right">Recorded P&amp;L</th>
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
              const isProfit = (t.realized_pnl ?? 0) > 0;
              const isLoss = (t.realized_pnl ?? 0) < 0;

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
                      <span className={isProfit ? "text-emerald-400" : isLoss ? "text-rose-400" : "text-slate-300"}>
                        {isProfit ? "+" : ""}{formatMoney(t.realized_pnl ?? 0)}
                        {t.pnl_source && t.pnl_source !== "unknown" ? <span className="ml-1 text-[9px] text-slate-500">{t.pnl_source.replaceAll("_", " ")}</span> : null}
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
                  No recent orders recorded in the trade log.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-[11px] text-slate-500">Recent trade records (latest {trades.length < 100 ? trades.length : 100}). Full-history totals above are calculated server-side.</p>
    </div>
  );
}

function formatMoney(value: number) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function BenchmarkMetric({ label, value, detail, tone = "neutral" }: { label: string; value: string; detail: string; tone?: "neutral" | "positive" | "negative" }) {
  const toneClass = tone === "positive" ? "text-emerald-300" : tone === "negative" ? "text-rose-300" : "text-slate-100";
  return <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3"><p className="text-[11px] uppercase tracking-wide text-slate-400">{label}</p><p className={`mt-1 text-xl font-semibold font-mono ${toneClass}`}>{value}</p><p className="mt-1 text-[10px] leading-relaxed text-slate-500">{detail}</p></div>;
}

function BenchmarkBreakdown({ title, rows }: { title: string; rows: TradeBenchmarkGroup[] }) {
  return <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-3"><h4 className="text-xs font-semibold text-slate-200">{title}</h4><div className="mt-2 divide-y divide-slate-800/70">{rows.map((row) => <div key={row.key} className="flex flex-wrap items-center justify-between gap-2 py-2 text-xs"><div className="min-w-0"><p className="truncate font-medium text-slate-200">{row.key}</p><p className="mt-0.5 text-[10px] text-slate-500">{row.scoredCount} scored · {row.wins}W / {row.losses}L / {row.breakeven}BE · win {row.winRatePct == null ? "—" : `${row.winRatePct.toFixed(0)}%`}</p></div><div className="text-right font-mono"><p className={row.netPnlAfterRecordedFees >= 0 ? "text-emerald-300" : "text-rose-300"}>{formatMoney(row.netPnlAfterRecordedFees)}</p><p className="mt-0.5 text-[10px] text-slate-500">expectancy {row.expectancy == null ? "—" : formatMoney(row.expectancy)}</p></div></div>)}</div></section>;
}
