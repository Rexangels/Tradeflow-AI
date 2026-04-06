import { useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";

export function SettingsPage() {
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: api.getSettings });
  const systemStatus = settingsQuery.data?.systemStatus;
  const riskPolicy = settingsQuery.data?.riskPolicy;

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Product posture</p>
        <h3 className="mt-2 text-3xl font-semibold">{settingsQuery.data?.planName ?? "Founding Operator"}</h3>
        <p className="mt-3 max-w-2xl text-slate-300">
          Live trading stays disabled in v1. The product is currently optimized for repeatable research, paper execution, and AI-assisted operator review.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-3xl border border-slate-800 bg-slate-950/80 p-5">
          <p className="text-sm text-slate-400">Backtests</p>
          <p className="mt-2 text-3xl font-semibold">{settingsQuery.data?.monthlyUsage.backtests ?? 0}</p>
        </div>
        <div className="rounded-3xl border border-slate-800 bg-slate-950/80 p-5">
          <p className="text-sm text-slate-400">AI messages</p>
          <p className="mt-2 text-3xl font-semibold">{settingsQuery.data?.monthlyUsage.aiMessages ?? 0}</p>
        </div>
        <div className="rounded-3xl border border-slate-800 bg-slate-950/80 p-5">
          <p className="text-sm text-slate-400">Paper orders</p>
          <p className="mt-2 text-3xl font-semibold">{settingsQuery.data?.monthlyUsage.paperOrders ?? 0}</p>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-2">
        <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">System status</p>
          <div className="mt-4 space-y-3 text-sm text-slate-300">
            <p>Database engine: {systemStatus?.databaseEngine ?? "unknown"}</p>
            <p>SQLite mode: {systemStatus?.sqliteMode ? "Enabled for local proof-of-concept" : "Disabled"}</p>
            <p>Gemini configured: {systemStatus?.geminiConfigured ? "Yes" : "No"}</p>
            <p>Market data provider: {systemStatus?.marketDataProviderUrl ?? "unknown"}</p>
            <p>Market data fallback: {systemStatus?.marketDataFallbackMode ?? "unknown"}</p>
            <p>Paper trading enabled: {systemStatus?.paperTradingEnabled ? "Yes" : "No"}</p>
            <p>Live trading enabled: {systemStatus?.liveTradingEnabled ? "Yes" : "No"}</p>
          </div>
        </div>

        <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Risk policy</p>
          <div className="mt-4 space-y-3 text-sm text-slate-300">
            <p>Trading kill switch: {riskPolicy?.tradingEnabled ? "Off" : "On"}</p>
            <p>Max order notional: ${(riskPolicy?.maxOrderNotional ?? 0).toFixed(2)}</p>
            <p>Max open positions: {riskPolicy?.maxOpenPositions ?? 0}</p>
            <p>Current open positions: {riskPolicy?.currentOpenPositions ?? 0}</p>
            <p>Daily loss limit: ${(riskPolicy?.maxDailyLoss ?? 0).toFixed(2)}</p>
            <p>Current daily realized loss: ${(riskPolicy?.dailyRealizedLoss ?? 0).toFixed(2)}</p>
          </div>
        </div>
      </section>
    </div>
  );
}
