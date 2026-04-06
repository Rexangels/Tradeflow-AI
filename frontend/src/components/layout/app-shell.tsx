import { LogOut, Radar, Settings, TestTube2, Wallet, Waypoints } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { queryClient } from "../../lib/query-client";
import { cn } from "../../lib/utils";
import { POPULAR_MARKETS, TIMEFRAME_OPTIONS } from "../../lib/workspace-options";
import { useWorkspaceStore } from "../../stores/workspace-store";

const navItems = [
  { to: "/", label: "Dashboard", icon: Radar },
  { to: "/agents", label: "Agents", icon: Waypoints },
  { to: "/backtests", label: "Backtests", icon: TestTube2 },
  { to: "/market-data", label: "Market Data", icon: Radar },
  { to: "/paper-trading", label: "Paper Trading", icon: Wallet },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function AppShell() {
  const { symbol, timeframe, setSymbol, setTimeframe } = useWorkspaceStore();
  const selectedMarket = POPULAR_MARKETS.includes(symbol as (typeof POPULAR_MARKETS)[number]) ? symbol : "CUSTOM";
  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(14,165,233,0.16),_transparent_36%),linear-gradient(180deg,_#050816,_#0f172a)] text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-[1600px]">
        <aside className="hidden w-72 shrink-0 border-r border-slate-800/80 bg-slate-950/60 px-6 py-8 backdrop-blur xl:block">
          <div className="rounded-3xl border border-cyan-500/20 bg-cyan-500/10 p-5">
            <p className="text-xs uppercase tracking-[0.28em] text-cyan-200/70">TradeFlow AI</p>
            <h1 className="mt-3 text-3xl font-semibold">Crypto research cockpit</h1>
            <p className="mt-2 text-sm text-slate-300">
              Paper-first strategy research with Django-backed state, deterministic backtests, and operator controls.
            </p>
          </div>

          <nav className="mt-8 space-y-2">
            {navItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm transition-colors",
                    isActive ? "bg-slate-100 text-slate-950" : "text-slate-300 hover:bg-slate-900/60",
                  )
                }
              >
                <Icon className="h-4 w-4" />
                {label}
              </NavLink>
            ))}
          </nav>

          <button
            type="button"
            onClick={() => logoutMutation.mutate()}
            className="mt-8 flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-800 bg-slate-900/80 px-4 py-3 text-sm text-slate-200"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-slate-950/70 px-5 py-4 backdrop-blur">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">Workspace</p>
                <h2 className="text-2xl font-semibold">Binance spot research desk</h2>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <select
                  aria-label="Popular markets"
                  value={selectedMarket}
                  onChange={(event) => {
                    if (event.target.value !== "CUSTOM") {
                      setSymbol(event.target.value);
                    }
                  }}
                  className="rounded-2xl border border-slate-700 bg-slate-950/90 px-4 py-2 text-sm outline-none"
                >
                  {POPULAR_MARKETS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                  <option value="CUSTOM">Custom</option>
                </select>
                <input
                  aria-label="Market symbol"
                  value={symbol}
                  onChange={(event) => setSymbol(event.target.value)}
                  placeholder="ETHUSDT"
                  className="rounded-2xl border border-slate-700 bg-slate-950/90 px-4 py-2 text-sm outline-none"
                />
                <select
                  aria-label="Timeframe"
                  value={timeframe}
                  onChange={(event) => setTimeframe(event.target.value as typeof timeframe)}
                  className="rounded-2xl border border-slate-700 bg-slate-950/90 px-4 py-2 text-sm outline-none"
                >
                  {TIMEFRAME_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </header>

          <main className="flex-1 px-5 py-6">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
