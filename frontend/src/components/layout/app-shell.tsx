import {
  CandlestickChart as ChartIcon,
  LogOut,
  Radar,
  Settings,
  TestTube2,
  Wallet,
  Waypoints,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { queryClient } from "../../lib/query-client";
import { cn } from "../../lib/utils";
import { POPULAR_MARKETS, TIMEFRAME_OPTIONS } from "../../lib/workspace-options";
import { useWorkspaceStore } from "../../stores/workspace-store";

const navItems = [
  { to: "/", label: "Dashboard", icon: Radar },
  { to: "/market-data", label: "Watchlist & Charts", icon: ChartIcon },
  { to: "/paper-trading", label: "Alpaca Execution Desk", icon: Wallet },
  { to: "/agents", label: "Strategy Agents", icon: Waypoints },
  { to: "/backtests", label: "Backtesting", icon: TestTube2 },
  { to: "/settings", label: "Risk & Settings", icon: Settings },
];

export function AppShell() {
  const { symbol, timeframe, setSymbol, setTimeframe } = useWorkspaceStore();

  const accountQuery = useQuery({
    queryKey: ["trading-account"],
    queryFn: api.getTradingAccount,
    refetchInterval: 8000,
  });

  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });

  const account = accountQuery.data;
  const isPaper = (account?.mode ?? "paper") === "paper";

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.14),_transparent_38%),linear-gradient(180deg,_#030712,_#0b1120)] text-slate-100 font-sans">
      <div className="mx-auto flex min-h-screen max-w-[1700px]">
        {/* Sidebar */}
        <aside className="hidden w-72 shrink-0 border-r border-slate-800/80 bg-slate-950/80 px-6 py-8 backdrop-blur xl:flex xl:flex-col xl:justify-between">
          <div>
            <div className="rounded-3xl border border-cyan-500/20 bg-gradient-to-b from-cyan-950/40 to-slate-900/60 p-5 shadow-lg shadow-cyan-950/20">
              <div className="flex items-center justify-between">
                <span className="text-[11px] uppercase tracking-[0.26em] font-bold text-cyan-400">
                  TradeFlow AI
                </span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider",
                    isPaper
                      ? "bg-amber-400/10 text-amber-300 border border-amber-400/20"
                      : "bg-emerald-400/10 text-emerald-300 border border-emerald-400/20",
                  )}
                >
                  {isPaper ? "Paper API" : "Live Broker"}
                </span>
              </div>
              <h1 className="mt-2 text-xl font-bold text-slate-100">
                Forex Trading Terminal
              </h1>
              <p className="mt-1.5 text-xs text-slate-400 leading-relaxed">
                Autonomous AI agents, institutional risk rules, and direct Alpaca execution.
              </p>
            </div>

            <nav className="mt-8 space-y-1.5">
              {navItems.map(({ to, label, icon: Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition-all duration-150",
                      isActive
                        ? "bg-gradient-to-r from-cyan-500 to-blue-600 text-slate-950 font-semibold shadow-md shadow-cyan-500/20"
                        : "text-slate-300 hover:bg-slate-900/80 hover:text-slate-100",
                    )
                  }
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>

          <div className="space-y-3 pt-6 border-t border-slate-800/60">
            {account && (
              <div className="rounded-2xl border border-slate-800/80 bg-slate-900/50 p-3.5 text-xs">
                <div className="flex items-center justify-between text-slate-400">
                  <span>Alpaca Equity</span>
                  <span className="font-mono font-bold text-slate-100">
                    ${account.equity.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="mt-1.5 flex items-center justify-between text-slate-400">
                  <span>Open Positions</span>
                  <span className="font-mono text-cyan-300 font-semibold">
                    {account.openPositionsCount ?? 0}
                  </span>
                </div>
              </div>
            )}

            <button
              type="button"
              onClick={() => logoutMutation.mutate()}
              className="flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-800/80 bg-slate-900/60 px-4 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-900 hover:text-slate-100 transition-colors"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign out
            </button>
          </div>
        </aside>

        {/* Main Workspace Area */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/80 px-6 py-3.5 backdrop-blur">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-center gap-3">
                <div className="h-2.5 w-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase tracking-[0.2em] font-bold text-slate-400">
                      Market Watch
                    </span>
                    <span className="text-xs font-mono text-cyan-400 font-bold">
                      {symbol}
                    </span>
                  </div>
                  <h2 className="text-lg font-bold text-slate-100">
                    Alpaca Forex Strategy Desk
                  </h2>
                </div>
              </div>

              {/* Controls & Quick Selector */}
              <div className="flex flex-wrap items-center gap-2.5">
                <div className="flex items-center gap-1.5 rounded-2xl border border-slate-800 bg-slate-900/80 p-1">
                  <select
                    aria-label="Active Forex Pair"
                    value={symbol}
                    onChange={(e) => setSymbol(e.target.value)}
                    className="rounded-xl bg-slate-950 px-3 py-1.5 text-xs font-semibold text-slate-100 outline-none border border-slate-700/60"
                  >
                    {POPULAR_MARKETS.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>

                  <div className="flex items-center gap-1 pl-1">
                    {TIMEFRAME_OPTIONS.map((tf) => (
                      <button
                        key={tf}
                        type="button"
                        onClick={() => setTimeframe(tf)}
                        className={cn(
                          "rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors",
                          timeframe === tf
                            ? "bg-cyan-500 text-slate-950"
                            : "text-slate-400 hover:text-slate-200",
                        )}
                      >
                        {tf}
                      </button>
                    ))}
                  </div>
                </div>

                {account && (
                  <div className="hidden sm:flex items-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 px-3.5 py-1.5 text-xs font-mono">
                    <span className="text-slate-400">Power:</span>
                    <span className="font-bold text-emerald-400">
                      ${account.buying_power.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </header>

          <main className="flex-1 p-6 overflow-y-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
