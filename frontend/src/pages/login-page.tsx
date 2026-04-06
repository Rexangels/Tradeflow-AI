import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";

import { useSession } from "../hooks/use-session";
import { api } from "../lib/api";
import { queryClient } from "../lib/query-client";

export function LoginPage() {
  const sessionQuery = useSession();
  const [email, setEmail] = useState("admin@tradeflow.local");
  const [password, setPassword] = useState("change-me");
  const loginMutation = useMutation({
    mutationFn: () => api.login(email, password),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session"] });
    },
  });

  if (sessionQuery.data?.isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,_rgba(34,197,94,0.18),_transparent_34%),linear-gradient(180deg,_#020617,_#111827)] px-6 text-slate-100">
      <div className="grid max-w-5xl gap-8 lg:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-[2rem] border border-emerald-500/20 bg-emerald-500/10 p-8">
          <p className="text-xs uppercase tracking-[0.28em] text-emerald-200/80">TradeFlow AI</p>
          <h1 className="mt-4 text-5xl font-semibold leading-tight">Launch the Django-backed crypto research platform.</h1>
          <p className="mt-4 max-w-xl text-lg text-slate-200/85">
            Backtests, paper execution, market-data caching, and AI orchestration now run server-side so the frontend stays focused on operator workflow.
          </p>
        </section>

        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-8 shadow-[0_20px_80px_rgba(2,6,23,0.5)]">
          <h2 className="text-2xl font-semibold">Admin operator sign-in</h2>
          <p className="mt-2 text-sm text-slate-400">Use the single-admin credentials defined in your Django environment.</p>

          <form
            className="mt-8 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              loginMutation.mutate();
            }}
          >
            <label className="block">
              <span className="mb-2 block text-sm text-slate-400">Email</span>
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm text-slate-400">Password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none"
              />
            </label>
            <button
              type="submit"
              disabled={loginMutation.isPending}
              className="w-full rounded-2xl bg-emerald-400 px-4 py-3 font-semibold text-slate-950 transition hover:bg-emerald-300 disabled:opacity-70"
            >
              {loginMutation.isPending ? "Signing in..." : "Enter research cockpit"}
            </button>
            {loginMutation.error ? (
              <p className="text-sm text-rose-300">{(loginMutation.error as Error).message}</p>
            ) : null}
          </form>
        </section>
      </div>
    </div>
  );
}
