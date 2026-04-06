import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../lib/api";
import { queryClient } from "../lib/query-client";
import type { AgentConfig, Strategy } from "../shared";
import { useWorkspaceStore } from "../stores/workspace-store";

function emptyAgent(): Omit<AgentConfig, "id" | "createdAt" | "updatedAt"> {
  return {
    name: "Trend Research Template",
    type: "template",
    rewardStyle: "balanced",
    riskTolerance: 0.4,
    holdingBehavior: "short-term",
    strategies: [
      { id: "trend-following", name: "Trend Following", description: "EMA crossover entries with momentum-aware exits.", enabled: true },
      { id: "mean-reversion", name: "Mean Reversion", description: "Bollinger fades filtered by RSI.", enabled: false },
    ],
  };
}

export function AgentsPage() {
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });
  const { selectedAgent, setSelectedAgent } = useWorkspaceStore();
  const [form, setForm] = useState<Omit<AgentConfig, "id" | "createdAt" | "updatedAt">>(emptyAgent());

  useEffect(() => {
    if (!selectedAgent && agentsQuery.data?.length) {
      setSelectedAgent(agentsQuery.data[0] ?? null);
    }
  }, [agentsQuery.data, selectedAgent, setSelectedAgent]);

  useEffect(() => {
    if (selectedAgent) {
      const { id, createdAt, updatedAt, ...rest } = selectedAgent;
      void id;
      void createdAt;
      void updatedAt;
      setForm(rest);
    }
  }, [selectedAgent]);

  const saveMutation = useMutation({
    mutationFn: () =>
      selectedAgent
        ? api.updateAgent(selectedAgent.id, form)
        : api.createAgent(form),
    onSuccess: (agent) => {
      setSelectedAgent(agent);
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    },
  });

  const activeStrategies = useMemo(() => form.strategies.filter((strategy) => strategy.enabled).length, [form.strategies]);

  const toggleStrategy = (strategyId: string) => {
    setForm((current) => ({
      ...current,
      strategies: current.strategies.map((strategy) =>
        strategy.id === strategyId ? { ...strategy, enabled: !strategy.enabled } : strategy,
      ),
    }));
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
        <div className="flex items-center justify-between">
          <h3 className="text-2xl font-semibold">Saved agents</h3>
          <button
            type="button"
            onClick={() => {
              setSelectedAgent(null);
              setForm(emptyAgent());
            }}
            className="rounded-2xl border border-slate-700 px-4 py-2 text-sm"
          >
            New agent
          </button>
        </div>

        <div className="mt-5 space-y-3">
          {(agentsQuery.data ?? []).map((agent) => (
            <button
              key={agent.id}
              type="button"
              onClick={() => setSelectedAgent(agent)}
              className="w-full rounded-3xl border border-slate-800 bg-slate-900/60 p-4 text-left"
            >
              <p className="font-medium">{agent.name}</p>
              <p className="mt-1 text-sm text-slate-400">
                {agent.rewardStyle} • risk {agent.riskTolerance.toFixed(1)}
              </p>
            </button>
          ))}
        </div>
      </section>

      <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
        <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Agent Editor</p>
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-2 block text-sm text-slate-400">Name</span>
            <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none" />
          </label>
          <label className="block">
            <span className="mb-2 block text-sm text-slate-400">Reward Style</span>
            <select value={form.rewardStyle} onChange={(event) => setForm({ ...form, rewardStyle: event.target.value as AgentConfig["rewardStyle"] })} className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none">
              <option value="balanced">Balanced</option>
              <option value="aggressive">Aggressive</option>
              <option value="conservative">Conservative</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm text-slate-400">Holding Behavior</span>
            <select value={form.holdingBehavior} onChange={(event) => setForm({ ...form, holdingBehavior: event.target.value as AgentConfig["holdingBehavior"] })} className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 outline-none">
              <option value="short-term">Short-term</option>
              <option value="swing">Swing</option>
              <option value="long-term">Long-term</option>
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-sm text-slate-400">Risk Tolerance</span>
            <input type="range" min="0" max="1" step="0.1" value={form.riskTolerance} onChange={(event) => setForm({ ...form, riskTolerance: Number(event.target.value) })} className="mt-4 w-full" />
          </label>
        </div>

        <div className="mt-6 rounded-3xl border border-slate-800 bg-slate-900/60 p-4">
          <p className="text-sm text-slate-400">Enabled strategies</p>
          <div className="mt-4 space-y-3">
            {form.strategies.map((strategy: Strategy) => (
              <button key={strategy.id} type="button" onClick={() => toggleStrategy(strategy.id)} className="flex w-full items-center justify-between rounded-2xl border border-slate-800 bg-slate-950/80 px-4 py-3 text-left">
                <div>
                  <p>{strategy.name}</p>
                  <p className="text-sm text-slate-500">{strategy.description}</p>
                </div>
                <span className={strategy.enabled ? "text-emerald-300" : "text-slate-500"}>{strategy.enabled ? "On" : "Off"}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="mt-6 flex items-center justify-between rounded-3xl border border-slate-800 bg-cyan-500/10 p-4">
          <p className="text-sm text-cyan-100">{activeStrategies} strategies enabled for execution.</p>
          <button type="button" onClick={() => saveMutation.mutate()} className="rounded-2xl bg-cyan-300 px-4 py-3 font-semibold text-slate-950">
            {saveMutation.isPending ? "Saving..." : selectedAgent ? "Update agent" : "Create agent"}
          </button>
        </div>
      </section>
    </div>
  );
}
