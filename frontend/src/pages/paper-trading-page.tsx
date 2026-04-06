import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { MetricCard } from "../components/ui/metric-card";
import { api } from "../lib/api";
import { queryClient } from "../lib/query-client";
import { useWorkspaceStore } from "../stores/workspace-store";
import type { PaperAccount, PaperOrder } from "../shared";

interface OrderInsight {
  title: string;
  lines: string[];
}

export function PaperTradingPage() {
  const { symbol, timeframe } = useWorkspaceStore();
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [notional, setNotional] = useState("250");
  const [lastOrderInsight, setLastOrderInsight] = useState<OrderInsight | null>(null);
  const accountQuery = useQuery({ queryKey: ["paper-account"], queryFn: api.getPaperAccount });

  const orderMutation = useMutation({
    mutationFn: () =>
      api.placePaperOrder({
        symbol,
        side,
        timeframe,
        notional: Number(notional),
      }),
    onMutate: () => {
      const previousAccount = queryClient.getQueryData<PaperAccount>(["paper-account"]) ?? accountQuery.data;
      return { previousAccount };
    },
    onSuccess: (payload, _variables, context) => {
      queryClient.setQueryData(["paper-account"], payload.account);
      queryClient.invalidateQueries({ queryKey: ["paper-account"] });
      setLastOrderInsight(buildOrderInsight(payload.order, payload.account, context?.previousAccount));
      setNotional("250");
    },
  });

  const account = accountQuery.data;
  const orderError = orderMutation.error ? (orderMutation.error as Error).message : null;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Cash" value={`$${(account?.cashBalance ?? 0).toFixed(2)}`} />
        <MetricCard label="Equity" value={`$${(account?.equity ?? 0).toFixed(2)}`} tone="positive" />
        <MetricCard label="Realized P&L" value={`$${(account?.realizedPnl ?? 0).toFixed(2)}`} />
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Max Order" value={`$${(account?.riskPolicy.maxOrderNotional ?? 0).toFixed(0)}`} />
        <MetricCard label="Max Positions" value={String(account?.riskPolicy.maxOpenPositions ?? 0)} />
        <MetricCard label="Open Positions" value={String(account?.riskPolicy.currentOpenPositions ?? 0)} />
        <MetricCard label="Daily Loss Limit" value={`$${(account?.riskPolicy.maxDailyLoss ?? 0).toFixed(0)}`} tone="warning" />
      </div>

      <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <div className="space-y-6">
          <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Place simulated order</p>
            <div className="mt-5 space-y-4">
              <label className="block">
                <span className="mb-2 block text-sm text-slate-400">Symbol</span>
                <input value={symbol} disabled className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none" />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm text-slate-400">Side</span>
                <select
                  value={side}
                  onChange={(event) => setSide(event.target.value as "buy" | "sell")}
                  className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none"
                >
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                </select>
              </label>
              <label className="block">
                <span className="mb-2 block text-sm text-slate-400">Notional</span>
                <input
                  value={notional}
                  onChange={(event) => setNotional(event.target.value)}
                  className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none"
                />
              </label>
              <button type="button" onClick={() => orderMutation.mutate()} className="w-full rounded-2xl bg-amber-300 px-4 py-3 font-semibold text-slate-950">
                {orderMutation.isPending ? "Submitting..." : "Execute paper order"}
              </button>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
                A buy converts cash into a position. A sell reduces the position and is the moment realized P&L becomes real on the account.
              </div>
              {orderError ? (
                <div className="rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
                  {orderError}
                </div>
              ) : null}
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">How to read this</p>
            <div className="mt-4 space-y-3 text-sm text-slate-300">
              <p>Cash is uninvested buying power left in the paper account.</p>
              <p>Equity is cash plus the current market value of all open paper positions.</p>
              <p>Realized P&L only changes when you sell. Price movement on an open position shows up as unrealized P&L instead.</p>
            </div>
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">What just happened</p>
            {lastOrderInsight ? (
              <div className="mt-4 space-y-3">
                <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 p-4 text-sm text-emerald-100">
                  {lastOrderInsight.title}
                </div>
                {lastOrderInsight.lines.map((line) => (
                  <div key={line} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-200">
                    {line}
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
                After you execute a paper order, this panel will explain the fill price, fee, cash movement, and whether P&L is still unrealized or already locked in.
              </div>
            )}
          </div>

          <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Open positions</p>
            <div className="mt-5 space-y-3">
              {(account?.positions ?? []).map((position) => (
                <div key={position.id} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <div className="flex items-center justify-between">
                    <p className="font-medium">{position.symbol}</p>
                    <p className={position.unrealizedPnl >= 0 ? "text-emerald-300" : "text-rose-300"}>
                      {position.unrealizedPnl >= 0 ? "+" : "-"}${Math.abs(position.unrealizedPnl).toFixed(2)}
                    </p>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2 text-sm text-slate-300">
                    <p>Qty {position.quantity.toFixed(6)}</p>
                    <p>Avg entry ${position.averageEntryPrice.toFixed(2)}</p>
                    <p>Market price ${position.marketPrice.toFixed(2)}</p>
                    <p>Market value ${position.marketValue.toFixed(2)}</p>
                  </div>
                </div>
              ))}
              {(account?.positions ?? []).length === 0 ? (
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
                  No open positions yet. A buy order will create one here.
                </div>
              ) : null}
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Recent fills</p>
            <div className="mt-5 space-y-3">
              {(account?.recentOrders ?? []).slice(0, 6).map((order) => (
                <div key={order.id} className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 text-sm">
                  <div className="flex items-center justify-between">
                    <span className={order.side === "buy" ? "text-emerald-300" : "text-sky-300"}>{order.side.toUpperCase()}</span>
                    <span>${order.notional.toFixed(2)}</span>
                  </div>
                  <div className="mt-2 grid gap-2 md:grid-cols-2 text-slate-300">
                    <p>Fill ${order.fillPrice.toFixed(2)}</p>
                    <p>Qty {order.quantity.toFixed(6)}</p>
                    <p>Fee ${order.feePaid.toFixed(2)}</p>
                    <p>Realized {order.realizedPnl >= 0 ? "+" : "-"}${Math.abs(order.realizedPnl).toFixed(2)}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}


function buildOrderInsight(order: PaperOrder, nextAccount: PaperAccount, previousAccount?: PaperAccount): OrderInsight {
  const cashBefore = previousAccount?.cashBalance ?? nextAccount.cashBalance;
  const equityBefore = previousAccount?.equity ?? nextAccount.equity;
  const realizedBefore = previousAccount?.realizedPnl ?? nextAccount.realizedPnl;
  const inferredCashDelta = order.side === "buy" ? -(order.notional + order.feePaid) : order.notional - order.feePaid;
  const inferredEquityDelta = order.side === "buy" ? -order.feePaid : order.realizedPnl;
  const inferredRealizedDelta = order.side === "sell" ? order.realizedPnl : 0;
  const cashDelta = previousAccount ? nextAccount.cashBalance - cashBefore : inferredCashDelta;
  const equityDelta = previousAccount ? nextAccount.equity - equityBefore : inferredEquityDelta;
  const realizedDelta = previousAccount ? nextAccount.realizedPnl - realizedBefore : inferredRealizedDelta;
  const actionVerb = order.side === "buy" ? "bought" : "sold";

  const lines = [
    `You ${actionVerb} ${order.quantity.toFixed(6)} units at ${order.fillPrice.toFixed(2)} and paid ${order.feePaid.toFixed(2)} in simulated fees.`,
    `Cash moved by ${formatSignedCurrency(cashDelta)} to ${nextAccount.cashBalance.toFixed(2)}.`,
    order.side === "buy"
      ? `Equity only moved by ${formatSignedCurrency(equityDelta)} because cash turned into an open position. Most of the immediate drop is just the trading fee.`
      : `Realized P&L moved by ${formatSignedCurrency(realizedDelta)} because selling is the moment the open trade becomes locked-in profit or loss.`,
    order.side === "buy"
      ? "Realized P&L stays unchanged until you sell. Until then, price movement shows up as unrealized P&L on the open position."
      : `Account equity is now ${nextAccount.equity.toFixed(2)} and any remaining position keeps floating with the market.`,
  ];

  return {
    title: `Paper ${order.side} executed for ${order.symbol}.`,
    lines,
  };
}


function formatSignedCurrency(value: number) {
  const sign = value >= 0 ? "+" : "-";
  return `${sign}$${Math.abs(value).toFixed(2)}`;
}
