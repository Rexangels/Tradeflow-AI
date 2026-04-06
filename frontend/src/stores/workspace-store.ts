import { create } from "zustand";

import { POPULAR_MARKETS } from "../lib/workspace-options";
import type { AgentConfig, BacktestResult, Timeframe } from "../shared";

interface WorkspaceState {
  symbol: string;
  timeframe: Timeframe;
  selectedAgent: AgentConfig | null;
  latestBacktest: BacktestResult | null;
  setSymbol: (symbol: string) => void;
  setTimeframe: (timeframe: Timeframe) => void;
  setSelectedAgent: (agent: AgentConfig | null) => void;
  setLatestBacktest: (result: BacktestResult | null) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  symbol: POPULAR_MARKETS[0],
  timeframe: "1h",
  selectedAgent: null,
  latestBacktest: null,
  setSymbol: (symbol) => set({ symbol: symbol.toUpperCase() }),
  setTimeframe: (timeframe) => set({ timeframe }),
  setSelectedAgent: (selectedAgent) => set({ selectedAgent }),
  setLatestBacktest: (latestBacktest) => set({ latestBacktest }),
}));
