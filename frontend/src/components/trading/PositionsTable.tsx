import { useMutation } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { queryClient } from "../../lib/query-client";
import type { TradingPosition } from "../../shared";
import { PositionDetailModal } from "./PositionDetailModal";

interface PositionsTableProps {
  positions: TradingPosition[];
  isLoading?: boolean;
}

export function PositionsTable({ positions, isLoading }: PositionsTableProps) {
  const [closingSymbol, setClosingSymbol] = useState<string | null>(null);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  const closeMutation = useMutation({
    mutationFn: (symbol: string) => api.closeTradingPosition(symbol),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trading-positions"] });
      queryClient.invalidateQueries({ queryKey: ["trading-account"] });
      queryClient.invalidateQueries({ queryKey: ["trading-orders"] });
      setClosingSymbol(null);
    },
  });

  const handleClose = (e: React.MouseEvent, symbol: string) => {
    e.stopPropagation();
    setClosingSymbol(symbol);
    closeMutation.mutate(symbol);
  };

  return (
    <>
      <div className="overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-950/70 backdrop-blur">
        <div className="flex items-center justify-between border-b border-slate-800/80 px-5 py-4">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-slate-100 text-base">Open Positions</h3>
              <span className="text-[11px] font-medium text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-500/20">
                Click any trade to track & AI protect
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Active exposure in your Alpaca account with live P&L and AI trailing stops
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              {positions.length} Active
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/60 uppercase tracking-wider text-slate-400 border-b border-slate-800/60">
              <tr>
                <th className="px-5 py-3 font-medium">Asset</th>
                <th className="px-4 py-3 font-medium">Side</th>
                <th className="px-4 py-3 font-medium text-right">Units</th>
                <th className="px-4 py-3 font-medium text-right">Avg Entry</th>
                <th className="px-4 py-3 font-medium text-right">Current Price</th>
                <th className="px-4 py-3 font-medium text-right">Market Value</th>
                <th className="px-4 py-3 font-medium text-right">Unrealized P&L</th>
                <th className="px-5 py-3 font-medium text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {positions.map((pos) => {
                const qty = Number(pos.qty ?? (pos as any).volume ?? 0);
                const avgEntry = Number(pos.avg_entry_price ?? (pos as any).entry_price ?? 0);
                const currentPx = Number(pos.current_price ?? avgEntry ?? 0);
                const pnl = Number(pos.unrealized_pnl ?? 0);
                const isProfit = pnl >= 0;
                const costBasis = Number(pos.cost_basis ?? (qty * avgEntry));
                const pnlPct = Number(
                  pos.unrealized_pnl_pct ?? (costBasis > 0 ? (pnl / costBasis) * 100 : 0)
                );
                const marketVal = Number(pos.market_value ?? (qty * currentPx));
                const isJpy = (pos.symbol || "").includes("JPY");
                const decimals = isJpy ? 3 : (currentPx > 100 ? 2 : (currentPx > 1 ? 4 : 5));

                return (
                  <tr
                    key={pos.symbol || (pos as any).ticket || Math.random()}
                    onClick={() => setSelectedSymbol(pos.symbol)}
                    className="hover:bg-indigo-950/20 hover:border-l-4 hover:border-l-indigo-500 transition-all cursor-pointer group"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-100 text-sm group-hover:text-indigo-400 transition-colors">
                          {pos.symbol}
                        </span>
                        <span className="opacity-0 group-hover:opacity-100 transition-opacity text-[10px] text-indigo-400 font-semibold bg-indigo-500/15 px-1.5 py-0.5 rounded">
                          Track & Protect →
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <span
                        className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase ${
                          (pos.side || "").toLowerCase() === "buy" || (pos.side || "").toLowerCase() === "long"
                            ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                            : "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                        }`}
                      >
                        {(pos.side || "HOLD").toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 font-mono text-right text-slate-200">
                      {qty.toLocaleString()}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-right text-slate-400">
                      ${avgEntry.toFixed(decimals)}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-right text-slate-200 font-medium">
                      ${currentPx.toFixed(decimals)}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-right text-slate-300">
                      ${marketVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="px-4 py-3.5 font-mono text-right">
                      <div
                        className={`inline-flex items-center gap-1 font-semibold ${
                          isProfit ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {isProfit ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                        <span>
                          {isProfit ? "+" : ""}${pnl.toFixed(2)}
                        </span>
                        <span className="text-[10px] font-normal opacity-80">
                          ({isProfit ? "+" : ""}{pnlPct.toFixed(2)}%)
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5 text-center">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedSymbol(pos.symbol);
                          }}
                          className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 px-3 py-1.5 text-xs font-semibold text-indigo-300 hover:bg-indigo-500/25 transition-colors"
                        >
                          AI Protect
                        </button>
                        <button
                          type="button"
                          disabled={closingSymbol === pos.symbol}
                          onClick={(e) => handleClose(e, pos.symbol)}
                          className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-500/25 transition-colors disabled:opacity-50"
                        >
                          {closingSymbol === pos.symbol ? "Closing..." : "Close"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!isLoading && positions.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-5 py-8 text-center text-slate-500">
                    <p className="text-sm">No open positions in Alpaca account.</p>
                    <p className="text-xs mt-1 text-slate-600">
                      Orders executed manually or by AI agents will appear here with live P&L.
                    </p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Position Detail Modal */}
      <PositionDetailModal
        symbol={selectedSymbol}
        isOpen={!!selectedSymbol}
        onClose={() => setSelectedSymbol(null)}
      />
    </>
  );
}

