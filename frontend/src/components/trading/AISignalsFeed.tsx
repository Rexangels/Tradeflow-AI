import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowUpRight, RefreshCw, Sparkles } from "lucide-react";
import { api } from "../../lib/api";
import { queryClient } from "../../lib/query-client";

interface AISignalsFeedProps {
  onSelectSymbol?: (symbol: string) => void;
}

export function AISignalsFeed({ onSelectSymbol }: AISignalsFeedProps) {
  const signalsQuery = useQuery({
    queryKey: ["ai-signals"],
    queryFn: api.getSignals,
    refetchInterval: 10000,
  });

  const scanMutation = useMutation({
    mutationFn: () => api.runAgentCycle(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ai-signals"] });
      queryClient.invalidateQueries({ queryKey: ["trading-positions"] });
      queryClient.invalidateQueries({ queryKey: ["trading-account"] });
      queryClient.invalidateQueries({ queryKey: ["trading-orders"] });
    },
  });

  const signals = signalsQuery.data ?? [];

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3.5">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-cyan-400" />
            <h3 className="font-semibold text-slate-100 text-base">AI Strategy Signals</h3>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Multi-indicator confluence signals (RSI, MACD, EMAs, ATR)
          </p>
        </div>
        <button
          type="button"
          disabled={scanMutation.isPending}
          onClick={() => scanMutation.mutate()}
          className="inline-flex items-center gap-1.5 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 text-xs font-semibold text-cyan-300 hover:bg-cyan-500/20 transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${scanMutation.isPending ? "animate-spin" : ""}`} />
          {scanMutation.isPending ? "Scanning..." : "Scan Markets"}
        </button>
      </div>

      <div className="mt-4 space-y-3 max-h-[480px] overflow-y-auto pr-1">
        {signals.map((sig) => {
          const isLong = sig.direction === "long";
          const isShort = sig.direction === "short";

          return (
            <div
              key={sig.id}
              onClick={() => onSelectSymbol?.(sig.symbol)}
              className="group cursor-pointer rounded-xl border border-slate-800/70 bg-slate-900/50 p-3 hover:border-slate-700 hover:bg-slate-900/80 transition-all"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-100 text-sm">
                    {sig.symbol}
                  </span>
                  <span
                    className={`inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                      isLong
                        ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                        : isShort
                        ? "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                        : "bg-slate-700/30 text-slate-400 border border-slate-700/40"
                    }`}
                  >
                    {isLong && <ArrowUpRight className="h-3 w-3" />}
                    {isShort && <ArrowDownRight className="h-3 w-3" />}
                    {sig.direction.toUpperCase()}
                  </span>
                  {sig.actedOn && (
                    <span className="rounded bg-cyan-500/20 px-1 py-0.2 text-[9px] font-semibold text-cyan-300">
                      ORDER PLACED
                    </span>
                  )}
                </div>
                <div className="text-right">
                  <span className="font-mono text-xs font-bold text-slate-200">
                    {sig.confidencePct}% Conf.
                  </span>
                </div>
              </div>

              {/* Confidence progress bar */}
              <div className="mt-2 h-1.5 w-full rounded-full bg-slate-800 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    isLong
                      ? "bg-emerald-400"
                      : isShort
                      ? "bg-rose-400"
                      : "bg-slate-500"
                  }`}
                  style={{ width: `${Math.min(100, Math.max(10, sig.confidencePct))}%` }}
                />
              </div>

              <p className="mt-2 text-xs text-slate-300 line-clamp-2">
                {sig.reasoning}
              </p>

              <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
                <span>{new Date(sig.createdAt).toLocaleTimeString()}</span>
                <span className="group-hover:text-cyan-400 transition-colors">
                  View Chart →
                </span>
              </div>
            </div>
          );
        })}

        {!signalsQuery.isLoading && signals.length === 0 && (
          <div className="rounded-xl border border-dashed border-slate-800 p-6 text-center text-slate-500">
            <p className="text-sm">No signals recorded yet.</p>
            <p className="text-xs mt-1">
              Click &quot;Scan Markets&quot; to run an automated technical cycle across all watched forex pairs.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
