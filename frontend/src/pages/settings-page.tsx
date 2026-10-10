import { useMutation, useQuery } from "@tanstack/react-query";
import { Globe } from "lucide-react";
import { RiskGuardrailCard } from "../components/trading/RiskGuardrailCard";
import { api } from "../lib/api";
import { queryClient } from "../lib/query-client";

export function SettingsPage() {
  const accountQuery = useQuery({
    queryKey: ["trading-account"],
    queryFn: api.getTradingAccount,
  });

  const pairsQuery = useQuery({
    queryKey: ["forex-pairs"],
    queryFn: api.getForexPairs,
  });

  const updatePairMutation = useMutation({
    mutationFn: ({ symbol, isWatched }: { symbol: string; isWatched: boolean }) =>
      api.updateForexPair(symbol, { isWatched }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["forex-pairs"] });
    },
  });

  const account = accountQuery.data;
  const pairs = pairsQuery.data ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <section className="rounded-3xl border border-slate-800/80 bg-gradient-to-r from-slate-950 via-slate-900/60 to-slate-950 p-6 backdrop-blur shadow-lg shadow-black/20">
        <p className="text-xs uppercase tracking-[0.24em] font-bold text-cyan-400">
          Broker & Risk Configuration
        </p>
        <h2 className="mt-1 text-2xl font-bold text-slate-100">
          Alpaca Connection & Risk Policy
        </h2>
        <p className="mt-1 text-xs text-slate-400 max-w-2xl">
          Configure active currency pair watchlists, view Alpaca broker credentials status, and manage server-side capital preservation rules.
        </p>
      </section>

      {/* Broker & API Connection Card */}
      <section className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <h3 className="font-semibold text-slate-100 text-sm">Alpaca Broker Connection</h3>
            <span className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-300">
              Connected & Verified
            </span>
          </div>

          <div className="mt-4 space-y-2.5 text-xs">
            <div className="flex items-center justify-between py-1 border-b border-slate-800/40">
              <span className="text-slate-400">Trading Mode</span>
              <span className="font-semibold text-amber-300 font-mono uppercase">
                {account?.mode ?? "paper"} (Simulated Real Money)
              </span>
            </div>
            <div className="flex items-center justify-between py-1 border-b border-slate-800/40">
              <span className="text-slate-400">API Endpoint</span>
              <span className="font-mono text-slate-300">
                https://paper-api.alpaca.markets/v2
              </span>
            </div>
            <div className="flex items-center justify-between py-1 border-b border-slate-800/40">
              <span className="text-slate-400">Account ID</span>
              <span className="font-mono text-slate-300">
                {account?.account_id ?? "Verified"}
              </span>
            </div>
            <div className="flex items-center justify-between py-1 border-b border-slate-800/40">
              <span className="text-slate-400">Trading Status</span>
              <span className="font-semibold text-emerald-400">
                {account?.status ?? "ACTIVE"}
              </span>
            </div>
            <div className="flex items-center justify-between py-1">
              <span className="text-slate-400">Switch to Live Money</span>
              <span className="text-[11px] text-slate-400">
                Set ALPACA_MODE=live in .env with live keys
              </span>
            </div>
          </div>
        </div>

        {/* Currency Pair Watchlist Manager */}
        <div className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 text-cyan-400" />
              <h3 className="font-semibold text-slate-100 text-sm">Currency Watchlist Manager</h3>
            </div>
            <span className="text-xs text-slate-400">
              {pairs.filter((p) => p.isWatched).length} Active Pairs
            </span>
          </div>

          <div className="mt-3.5 space-y-2 max-h-56 overflow-y-auto pr-1">
            {pairs.map((pair) => (
              <div
                key={pair.symbol}
                className="flex items-center justify-between rounded-xl border border-slate-800/70 bg-slate-900/40 px-3 py-2 text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-100">{pair.symbol}</span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    Mid: {pair.quote.mid.toFixed(pair.symbol.includes("JPY") ? 3 : 5)}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    updatePairMutation.mutate({
                      symbol: pair.symbol,
                      isWatched: !pair.isWatched,
                    })
                  }
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    pair.isWatched
                      ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
                      : "bg-slate-800 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {pair.isWatched ? "Active" : "Paused"}
                </button>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Risk Management Rule Inspector & Editor */}
      <RiskGuardrailCard />
    </div>
  );
}
