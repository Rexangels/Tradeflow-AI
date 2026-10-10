import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  Lock,
  Percent,
  RefreshCw,
  Shield,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  X,
} from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { queryClient } from "../../lib/query-client";

interface PositionDetailModalProps {
  symbol: string | null;
  isOpen: boolean;
  onClose: () => void;
}

export function PositionDetailModal({ symbol, isOpen, onClose }: PositionDetailModalProps) {
  const [trailPercent, setTrailPercent] = useState<number>(5.0);
  const [customStopLoss, setCustomStopLoss] = useState<string>("");
  const [customTakeProfit, setCustomTakeProfit] = useState<string>("");
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);

  const {
    data: details,
    isLoading,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["position-details", symbol],
    queryFn: () => (symbol ? api.getTradingPositionDetails(symbol) : null),
    enabled: isOpen && !!symbol,
    refetchInterval: 3000,
  });

  const {
    data: aiAdvice,
    mutate: fetchAiAdvice,
    isPending: isAdvicePending,
  } = useMutation({
    mutationFn: () => api.getTradingPositionAiAdvice(symbol!),
    onSuccess: (data) => {
      if (data.suggested_trail_percent) {
        setTrailPercent(data.suggested_trail_percent);
      }
      if (data.suggested_stop_loss) {
        setCustomStopLoss(data.suggested_stop_loss.toString());
      }
      if (data.suggested_take_profit) {
        setCustomTakeProfit(data.suggested_take_profit.toString());
      }
    },
  });

  const protectMutation = useMutation({
    mutationFn: (payload: {
      protect_type: "trailing_stop" | "stop_loss" | "breakeven" | "bracket";
      trail_percent?: number;
      stop_loss?: number;
      take_profit?: number;
    }) => api.protectTradingPosition(symbol!, payload),
    onSuccess: (data) => {
      setFeedbackMessage(data.message || "Protection successfully applied!");
      queryClient.invalidateQueries({ queryKey: ["position-details", symbol] });
      queryClient.invalidateQueries({ queryKey: ["trading-positions"] });
      queryClient.invalidateQueries({ queryKey: ["trading-orders"] });
      setTimeout(() => setFeedbackMessage(null), 5000);
    },
    onError: (err: any) => {
      setFeedbackMessage(err.message || "Failed to apply protection");
    },
  });

  const partialCloseMutation = useMutation({
    mutationFn: (percentage: number) =>
      api.closeTradingPositionPartial(symbol!, { percentage }),
    onSuccess: (data) => {
      setFeedbackMessage(`Successfully banked profit on ${data.closed_qty} units!`);
      queryClient.invalidateQueries({ queryKey: ["position-details", symbol] });
      queryClient.invalidateQueries({ queryKey: ["trading-positions"] });
      queryClient.invalidateQueries({ queryKey: ["trading-account"] });
      setTimeout(() => setFeedbackMessage(null), 5000);
    },
    onError: (err: any) => {
      setFeedbackMessage(err.message || "Partial close failed");
    },
  });

  const fullCloseMutation = useMutation({
    mutationFn: () => api.closeTradingPosition(symbol!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trading-positions"] });
      queryClient.invalidateQueries({ queryKey: ["trading-account"] });
      onClose();
    },
  });

  if (!isOpen || !symbol) return null;

  const isProfit = (details?.unrealized_pnl ?? 0) >= 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-3xl rounded-3xl border border-slate-700/80 bg-slate-900/95 shadow-2xl shadow-indigo-950/40 overflow-hidden flex flex-col max-h-[92vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-6 py-5 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 font-bold">
              <TrendingUp className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold tracking-tight text-white">{symbol}</h2>
                <span className="rounded-md bg-slate-800 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-slate-300">
                  {details?.asset_class === "us_equity" ? "US Stock" : details?.asset_class || "Asset"}
                </span>
                <span
                  className={`rounded-md px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider ${
                    details?.side === "long"
                      ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                      : "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                  }`}
                >
                  {details?.side?.toUpperCase()} • {details?.qty?.toLocaleString()} Units
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Active Position Guardian & Live Trailing Stop Control
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => refetch()}
              disabled={isFetching}
              className="rounded-xl border border-slate-800 bg-slate-800/50 p-2 text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title="Refresh Position"
            >
              <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin text-indigo-400" : ""}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-slate-800 bg-slate-800/50 p-2 text-slate-400 hover:text-white hover:bg-slate-800 transition"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Feedback Alert */}
        {feedbackMessage && (
          <div className="bg-emerald-500/10 border-b border-emerald-500/30 px-6 py-2.5 text-xs font-medium text-emerald-300 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span>{feedbackMessage}</span>
            </div>
            <button
              type="button"
              onClick={() => setFeedbackMessage(null)}
              className="text-slate-400 hover:text-white text-xs"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Modal Body */}
        <div className="overflow-y-auto p-6 space-y-6">
          {isLoading && !details ? (
            <div className="flex flex-col items-center justify-center py-12 text-slate-400 space-y-3">
              <RefreshCw className="h-8 w-8 animate-spin text-indigo-500" />
              <p className="text-sm">Fetching real-time trade data from Alpaca...</p>
            </div>
          ) : (
            <>
              {/* Hero P&L Banner */}
              <div className="rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-5 shadow-inner">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Unrealized P&L</span>
                    <div
                      className={`text-2xl font-black mt-1 flex items-center gap-1 ${
                        isProfit ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {isProfit ? <ArrowUpRight className="h-6 w-6" /> : <ArrowDownRight className="h-6 w-6" />}
                      <span>{isProfit ? "+" : ""}${details?.unrealized_pnl?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                    </div>
                    <span className="text-xs font-semibold text-emerald-400/90">
                      {isProfit ? "+" : ""}{details?.unrealized_pnl_pct}% Return
                    </span>
                  </div>

                  <div>
                    <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Avg Entry Price</span>
                    <p className="text-xl font-bold font-mono text-slate-200 mt-1">
                      ${details?.avg_entry_price?.toFixed(2)}
                    </p>
                    <span className="text-[11px] text-slate-500">Breakeven: ${details?.breakeven_price?.toFixed(2)}</span>
                  </div>

                  <div>
                    <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Current Market Price</span>
                    <p className="text-xl font-bold font-mono text-indigo-300 mt-1">
                      ${details?.current_price?.toFixed(2)}
                    </p>
                    <span className="text-[11px] text-slate-500">Live Alpaca feed</span>
                  </div>

                  <div>
                    <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Market Value</span>
                    <p className="text-xl font-bold font-mono text-slate-100 mt-1">
                      ${details?.market_value?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </p>
                    <span className="text-[11px] text-slate-500">{details?.qty} shares</span>
                  </div>
                </div>
              </div>

              {/* Protection Status Banner */}
              <div
                className={`rounded-2xl border p-4 ${
                  details?.is_protected
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                    : "border-amber-500/40 bg-amber-500/10 text-amber-200"
                }`}
              >
                <div className="flex items-start gap-3">
                  {details?.is_protected ? (
                    <Shield className="h-5 w-5 text-emerald-400 mt-0.5 shrink-0" />
                  ) : (
                    <ShieldAlert className="h-5 w-5 text-amber-400 mt-0.5 shrink-0" />
                  )}
                  <div className="flex-1 text-xs space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-sm tracking-wide">
                        {details?.is_protected ? "AI Trade Guardian ACTIVE" : "UNPROTECTED POSITION: HIGH RISK OF PROFIT GIVEBACK"}
                      </span>
                      {details?.is_protected && (
                        <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-300">
                          Active Orders Attached
                        </span>
                      )}
                    </div>
                    <p className="opacity-90 leading-relaxed">
                      {details?.is_protected
                        ? `This position has active stop protections on Alpaca. Trailing Stop: ${
                            details?.active_protection.trailing_stop
                              ? `${details.active_protection.trailing_stop.trail_percent}% trailing`
                              : "None"
                          } | Fixed SL: ${
                            details?.active_protection.stop_loss
                              ? `$${details.active_protection.stop_loss.stop_price}`
                              : "None"
                          }`
                        : details?.risk_alert ||
                          "No Stop Loss or Trailing Stop is active. If the market pulls back, you risk giving back all accumulated profits."}
                    </p>
                  </div>
                </div>
              </div>

              {/* AI Auto-Pilot Protection Action Row */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-indigo-400" />
                    AI Auto-Pilot Protection Controls
                  </h3>
                  <span className="text-xs text-slate-400">1-Click Capital & Profit Locks</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  {/* Action 1: Break-even Shield */}
                  <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 flex flex-col justify-between hover:border-indigo-500/50 transition">
                    <div>
                      <div className="flex items-center gap-2 text-indigo-400">
                        <Lock className="h-4 w-4" />
                        <span className="font-semibold text-xs text-white">Zero-Risk Breakeven</span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Moves Stop-Loss to <span className="text-indigo-300 font-mono">${details?.breakeven_price?.toFixed(2)}</span>.
                        Trade can NEVER turn into a loss!
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={protectMutation.isPending}
                      onClick={() => protectMutation.mutate({ protect_type: "breakeven" })}
                      className="mt-3 w-full rounded-xl bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition disabled:opacity-50"
                    >
                      {protectMutation.isPending ? "Applying..." : "Lock Breakeven"}
                    </button>
                  </div>

                  {/* Action 2: 5% Trailing Stop */}
                  <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 flex flex-col justify-between hover:border-emerald-500/50 transition">
                    <div>
                      <div className="flex items-center gap-2 text-emerald-400">
                        <TrendingUp className="h-4 w-4" />
                        <span className="font-semibold text-xs text-white">5% Dynamic Trailing</span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Follows price up. Currently stops @ <span className="text-emerald-300 font-mono">${details?.trailing_presets.balanced_5pct.stop_price}</span>, locking in <span className="text-emerald-400 font-semibold">+${details?.trailing_presets.balanced_5pct.guaranteed_pnl?.toLocaleString()}</span>!
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={protectMutation.isPending}
                      onClick={() => protectMutation.mutate({ protect_type: "trailing_stop", trail_percent: 5.0 })}
                      className="mt-3 w-full rounded-xl bg-emerald-600 px-3 py-2 text-xs font-semibold text-white hover:bg-emerald-500 transition disabled:opacity-50"
                    >
                      {protectMutation.isPending ? "Applying..." : "Activate 5% Trailing Stop"}
                    </button>
                  </div>

                  {/* Action 3: Partial Profit Taker */}
                  <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 flex flex-col justify-between hover:border-amber-500/50 transition">
                    <div>
                      <div className="flex items-center gap-2 text-amber-400">
                        <Percent className="h-4 w-4" />
                        <span className="font-semibold text-xs text-white">Bank Partial Profit</span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1">
                        Cash out a portion now to realize solid gains, leaving the remainder running risk-free.
                      </p>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        disabled={partialCloseMutation.isPending}
                        onClick={() => partialCloseMutation.mutate(25)}
                        className="rounded-xl border border-amber-500/30 bg-amber-500/15 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/30 transition disabled:opacity-50"
                      >
                        Bank 25%
                      </button>
                      <button
                        type="button"
                        disabled={partialCloseMutation.isPending}
                        onClick={() => partialCloseMutation.mutate(50)}
                        className="rounded-xl border border-amber-500/30 bg-amber-500/15 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/30 transition disabled:opacity-50"
                      >
                        Bank 50%
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* AI Gemini Diagnostic Advisor Box */}
              <div className="rounded-2xl border border-indigo-500/30 bg-indigo-950/20 p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Bot className="h-5 w-5 text-indigo-400" />
                    <h4 className="text-sm font-semibold text-white">Gemini AI Position Diagnostic</h4>
                  </div>
                  <button
                    type="button"
                    onClick={() => fetchAiAdvice()}
                    disabled={isAdvicePending}
                    className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition disabled:opacity-50"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {isAdvicePending ? "Analyzing Position..." : "Ask AI Strategic Plan"}
                  </button>
                </div>

                {aiAdvice?.ai_advice ? (
                  <div className="rounded-xl border border-indigo-900/50 bg-slate-950/70 p-4 text-xs text-slate-300 space-y-2 whitespace-pre-line leading-relaxed">
                    {aiAdvice.ai_advice}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 leading-relaxed">
                    Click <strong>Ask AI Strategic Plan</strong> to run an instant Gemini diagnostic on AAPL momentum,
                    recommended trailing percentage, and risk boundaries to prevent giving back profits.
                  </p>
                )}
              </div>

              {/* Custom Stop Loss & Trailing Percentage Form */}
              <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-5 space-y-4">
                <h4 className="text-sm font-semibold text-white">Customize Protection Levels</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">
                      Trailing Stop Percentage (%)
                    </label>
                    <div className="flex items-center gap-2">
                      {[3, 5, 8, 10].map((pct) => (
                        <button
                          key={pct}
                          type="button"
                          onClick={() => setTrailPercent(pct)}
                          className={`flex-1 rounded-xl py-1 text-xs font-bold border transition ${
                            trailPercent === pct
                              ? "bg-indigo-600 border-indigo-500 text-white"
                              : "bg-slate-900 border-slate-800 text-slate-400 hover:text-white"
                          }`}
                        >
                          {pct}%
                        </button>
                      ))}
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">
                      Fixed Stop Loss ($)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      placeholder={`e.g. ${details?.trailing_presets.balanced_5pct.stop_price}`}
                      value={customStopLoss}
                      onChange={(e) => setCustomStopLoss(e.target.value)}
                      className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs font-mono text-white placeholder-slate-600 focus:border-indigo-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">
                      Take Profit Target ($)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="e.g. 380.00"
                      value={customTakeProfit}
                      onChange={(e) => setCustomTakeProfit(e.target.value)}
                      className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-xs font-mono text-white placeholder-slate-600 focus:border-indigo-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="text-xs text-slate-400">
                    Applying protection cancels old conflicting orders and submits live to Alpaca.
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={protectMutation.isPending}
                      onClick={() =>
                        protectMutation.mutate({
                          protect_type: "trailing_stop",
                          trail_percent: trailPercent,
                        })
                      }
                      className="rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white hover:bg-indigo-500 transition disabled:opacity-50"
                    >
                      {protectMutation.isPending ? "Updating..." : `Set ${trailPercent}% Trailing Stop`}
                    </button>
                    {customStopLoss && customTakeProfit ? (
                      <button
                        type="button"
                        disabled={protectMutation.isPending}
                        onClick={() =>
                          protectMutation.mutate({
                            protect_type: "bracket",
                            stop_loss: parseFloat(customStopLoss),
                            take_profit: parseFloat(customTakeProfit),
                          })
                        }
                        className="rounded-xl border border-indigo-500/50 bg-indigo-900/40 px-4 py-2 text-xs font-semibold text-indigo-200 hover:bg-indigo-800/40 transition disabled:opacity-50"
                      >
                        Set Bracket (SL + TP)
                      </button>
                    ) : customStopLoss ? (
                      <button
                        type="button"
                        disabled={protectMutation.isPending}
                        onClick={() =>
                          protectMutation.mutate({
                            protect_type: "stop_loss",
                            stop_loss: parseFloat(customStopLoss),
                          })
                        }
                        className="rounded-xl border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition disabled:opacity-50"
                      >
                        Set Fixed SL (${customStopLoss})
                      </button>
                    ) : null}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 px-6 py-4 bg-slate-950/80">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-800 bg-slate-900 px-4 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 transition"
          >
            Close Window
          </button>

          <button
            type="button"
            disabled={fullCloseMutation.isPending}
            onClick={() => {
              if (window.confirm(`Are you sure you want to close the entire ${symbol} position?`)) {
                fullCloseMutation.mutate();
              }
            }}
            className="rounded-xl border border-rose-500/30 bg-rose-500/15 px-4 py-2 text-xs font-semibold text-rose-300 hover:bg-rose-500/30 transition disabled:opacity-50"
          >
            {fullCloseMutation.isPending ? "Liquidating..." : "Liquidate Entire Position (Market Sell)"}
          </button>
        </div>
      </div>
    </div>
  );
}
