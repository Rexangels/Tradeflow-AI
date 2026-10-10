import { useQuery } from "@tanstack/react-query";
import { MetricCard } from "../components/ui/metric-card";
import { OrderFormPanel } from "../components/trading/OrderFormPanel";
import { PositionsTable } from "../components/trading/PositionsTable";
import { RiskGuardrailCard } from "../components/trading/RiskGuardrailCard";
import { TradeJournalTable } from "../components/trading/TradeJournalTable";
import { api } from "../lib/api";
import { useWorkspaceStore } from "../stores/workspace-store";

export function PaperTradingPage() {
  const { symbol } = useWorkspaceStore();

  const accountQuery = useQuery({
    queryKey: ["trading-account"],
    queryFn: api.getTradingAccount,
    refetchInterval: 8000,
  });

  const positionsQuery = useQuery({
    queryKey: ["trading-positions"],
    queryFn: api.getTradingPositions,
    refetchInterval: 5000,
  });

  const account = accountQuery.data;
  const positions = positionsQuery.data ?? [];
  const unrealizedPnl = account?.totalUnrealizedPnl ?? 0;

  return (
    <div className="space-y-6">
      {/* Account Overview Header */}
      <section className="rounded-3xl border border-slate-800/80 bg-gradient-to-r from-slate-950 via-slate-900/60 to-slate-950 p-6 backdrop-blur shadow-lg shadow-black/20">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <p className="text-xs font-bold uppercase tracking-[0.24em] text-cyan-400">
                Alpaca Markets Live Desk
              </p>
            </div>
            <h2 className="mt-1 text-2xl font-bold text-slate-100">
              Execution Engine & Position Portfolio
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              Orders routed with server-side risk checks, attached stop-loss brackets, and live trade journaling.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="rounded-2xl border border-amber-400/30 bg-amber-400/10 px-3.5 py-1.5 text-xs font-semibold text-amber-300">
              Mode: {(account?.mode ?? "paper").toUpperCase()} TRADING
            </span>
            <span className="rounded-2xl border border-emerald-400/30 bg-emerald-400/10 px-3.5 py-1.5 text-xs font-semibold text-emerald-300">
              Status: {account?.status ?? "ACTIVE"}
            </span>
          </div>
        </div>
      </section>

      {/* Account Metrics Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Account Equity"
          value={`$${(account?.equity ?? 25000).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          tone="positive"
        />
        <MetricCard
          label="Available Cash"
          value={`$${(account?.cash ?? 25000).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
        <MetricCard
          label="Buying Power"
          value={`$${(account?.buying_power ?? 100000).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
        />
        <MetricCard
          label="Unrealized P&L"
          value={`${unrealizedPnl >= 0 ? "+" : ""}$${unrealizedPnl.toFixed(2)}`}
          tone={unrealizedPnl >= 0 ? "positive" : "warning"}
        />
      </div>

      {/* Positions & Order Submission Grid */}
      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-6">
          <PositionsTable positions={positions} isLoading={positionsQuery.isLoading} />
          <RiskGuardrailCard />
        </div>
        <div>
          <OrderFormPanel initialSymbol={symbol} />
        </div>
      </div>

      {/* Trade Audit Journal */}
      <TradeJournalTable />
    </div>
  );
}
