import { useMutation, useQuery } from "@tanstack/react-query";
import { Edit2, Shield } from "lucide-react";
import { useState } from "react";
import { api } from "../../lib/api";
import { queryClient } from "../../lib/query-client";

export function RiskGuardrailCard() {
  const [isEditing, setIsEditing] = useState(false);
  const [maxRiskPct, setMaxRiskPct] = useState("2.0");
  const [maxPositions, setMaxPositions] = useState("5");
  const [dailyLossLimitPct, setDailyLossLimitPct] = useState("5.0");
  const [minRrRatio, setMinRrRatio] = useState("1.5");

  const rulesQuery = useQuery({
    queryKey: ["risk-rules"],
    queryFn: async () => {
      const data = await api.getRiskRules();
      setMaxRiskPct(String(data.max_risk_pct ?? 2.0));
      setMaxPositions(String(data.max_positions ?? 5));
      setDailyLossLimitPct(String(data.daily_loss_limit_pct ?? 5.0));
      setMinRrRatio(String(data.min_rr_ratio ?? 1.5));
      return data;
    },
  });

  const updateMutation = useMutation({
    mutationFn: (newRules: Record<string, unknown>) => api.updateRiskRules(newRules),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risk-rules"] });
      queryClient.invalidateQueries({ queryKey: ["trading-account"] });
      setIsEditing(false);
    },
  });

  const handleSave = () => {
    updateMutation.mutate({
      max_risk_pct: parseFloat(maxRiskPct),
      max_positions: parseInt(maxPositions, 10),
      daily_loss_limit_pct: parseFloat(dailyLossLimitPct),
      min_rr_ratio: parseFloat(minRrRatio),
    });
  };

  const rules = rulesQuery.data;

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3.5">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-emerald-400" />
          <h3 className="font-semibold text-slate-100 text-base">Server-Enforced Risk Guardrails</h3>
        </div>
        {!isEditing ? (
          <button
            type="button"
            onClick={() => setIsEditing(true)}
            className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 font-medium transition-colors"
          >
            <Edit2 className="h-3 w-3" />
            Edit Rules
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="text-xs text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={updateMutation.isPending}
              className="rounded-lg bg-emerald-500 px-2.5 py-1 text-xs font-semibold text-slate-950 hover:bg-emerald-400 transition-colors"
            >
              {updateMutation.isPending ? "Saving..." : "Save"}
            </button>
          </div>
        )}
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* Max Risk % */}
        <div className="rounded-xl border border-slate-800/70 bg-slate-900/50 p-3">
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Max Risk / Trade</p>
          {isEditing ? (
            <input
              type="number"
              step="0.1"
              value={maxRiskPct}
              onChange={(e) => setMaxRiskPct(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm font-bold text-slate-100 font-mono"
            />
          ) : (
            <p className="mt-1 font-mono text-lg font-bold text-slate-100">
              {rules?.max_risk_pct ?? 2.0}%
            </p>
          )}
          <p className="text-[10px] text-slate-500 mt-0.5">Of total account equity</p>
        </div>

        {/* Max Open Positions */}
        <div className="rounded-xl border border-slate-800/70 bg-slate-900/50 p-3">
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Max Concurrent Pos.</p>
          {isEditing ? (
            <input
              type="number"
              value={maxPositions}
              onChange={(e) => setMaxPositions(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm font-bold text-slate-100 font-mono"
            />
          ) : (
            <p className="mt-1 font-mono text-lg font-bold text-slate-100">
              {rules?.max_positions ?? 5} Pairs
            </p>
          )}
          <p className="text-[10px] text-slate-500 mt-0.5">Prevents overexposure</p>
        </div>

        {/* Daily Loss Limit */}
        <div className="rounded-xl border border-slate-800/70 bg-slate-900/50 p-3">
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Daily Loss Circuit Breaker</p>
          {isEditing ? (
            <input
              type="number"
              step="0.5"
              value={dailyLossLimitPct}
              onChange={(e) => setDailyLossLimitPct(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm font-bold text-slate-100 font-mono"
            />
          ) : (
            <p className="mt-1 font-mono text-lg font-bold text-rose-400">
              {rules?.daily_loss_limit_pct ?? 5.0}%
            </p>
          )}
          <p className="text-[10px] text-slate-500 mt-0.5">Auto-halts all trading for the day</p>
        </div>

        {/* Minimum R:R */}
        <div className="rounded-xl border border-slate-800/70 bg-slate-900/50 p-3">
          <p className="text-[11px] text-slate-400 uppercase tracking-wider">Min Reward-to-Risk</p>
          {isEditing ? (
            <input
              type="number"
              step="0.1"
              value={minRrRatio}
              onChange={(e) => setMinRrRatio(e.target.value)}
              className="mt-1 w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm font-bold text-slate-100 font-mono"
            />
          ) : (
            <p className="mt-1 font-mono text-lg font-bold text-emerald-400">
              {rules?.min_rr_ratio ?? 1.5}R
            </p>
          )}
          <p className="text-[10px] text-slate-500 mt-0.5">Mandatory Stop-Loss: Active</p>
        </div>
      </div>
    </div>
  );
}
