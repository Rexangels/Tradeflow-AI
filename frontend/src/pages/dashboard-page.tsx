import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  BarChart2,
  Bot,
  CheckCircle2,
  ChevronRight,
  Compass,
  Cpu,
  MessageSquarePlus,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";

import { MarkdownRenderer } from "../components/ui/MarkdownRenderer";
import { CandlestickChart } from "../components/CandlestickChart";

import { api } from "../lib/api";
import { MetricCard } from "../components/ui/metric-card";
import { OrderFormPanel } from "../components/trading/OrderFormPanel";
import { PositionsTable } from "../components/trading/PositionsTable";
import { TradeJournalTable } from "../components/trading/TradeJournalTable";
import { InstitutionalEdgeRadar } from "../components/trading/InstitutionalEdgeRadar";
import { useWorkspaceStore } from "../stores/workspace-store";

// Preset one-click prompts so the user never has to guess what to type
const QUICK_COMMANDS = [
  {
    id: "best-trade",
    title: "Find Best Trade Right Now",
    desc: "Scans forex & crypto pairs — picks the highest-confidence setup",
    icon: Sparkles,
    prompt: "Scan the market right now across forex and crypto pairs. Which instrument (EUR/USD, GBP/USD, BTC/USD, ETH/USD, XAU/USD) has the highest confluence signal? Give me the exact direction, entry price, stop-loss, and take-profit for the best setup.",
  },
  {
    id: "analyze-active",
    title: "Analyze Active Pair",
    desc: "Plain-English verdict: Bullish, Bearish, or Stay Out",
    icon: TrendingUp,
    prompt: "Analyze the current pair in detail using top-down multi-timeframe analysis (4H, 1H, 15M). What are the RSI, MACD, and EMA trends saying? Is there institutional alignment? Should I enter or stay out?",
  },
  {
    id: "risk-audit",
    title: "Audit Account & Risk Limits",
    desc: "Verifies equity, open exposure, and daily loss circuit breaker",
    icon: ShieldCheck,
    prompt: "Audit my current Exness MT5 account status and risk rules. What is my equity, free margin, open positions, and is it safe to open a new trade today?",
  },
  {
    id: "execute-safely",
    title: "Suggest a Safe Order",
    desc: "Calculates exact 2% risk position sizing and 2.0R safety brackets",
    icon: Zap,
    prompt: "Propose a fully risk-managed trade for our active pair that strictly follows our 2% risk rule, mandatory stop-loss, and 1.5R minimum R:R. Include exact lot size for a $500 account.",
  },
];

export function DashboardPage() {
  const { symbol, timeframe, setSymbol } = useWorkspaceStore();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  // Persist threadId in localStorage so it survives page refresh
  const [threadId, setThreadId] = useState<string | undefined>(() => {
    return localStorage.getItem("tradeflow_thread_id") ?? undefined;
  });
  const [activeTab, setActiveTab] = useState<"ai-copilot" | "order-desk">("ai-copilot");
  const [selectedTradeSymbol, setSelectedTradeSymbol] = useState<string | null>(null);
  const [selectedTradeSide, setSelectedTradeSide] = useState<"buy" | "sell">("buy");
  const [aiScanStatus, setAiScanStatus] = useState<"idle" | "observing" | "analyzing" | "completed">("idle");
  const [aiLatestSummary, setAiLatestSummary] = useState<string | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  // Queries
  const accountQuery = useQuery({
    queryKey: ["trading-account"],
    queryFn: api.getTradingAccount,
    refetchInterval: 6000,
  });

  const pairsQuery = useQuery({
    queryKey: ["forex-pairs"],
    queryFn: api.getForexPairs,
    refetchInterval: 5000,
  });

  const positionsQuery = useQuery({
    queryKey: ["trading-positions"],
    queryFn: api.getTradingPositions,
    refetchInterval: 5000,
  });

  const signalsQuery = useQuery({
    queryKey: ["ai-signals"],
    queryFn: api.getSignals,
    refetchInterval: 8000,
  });

  // Candlestick chart data for the active pair
  const candlesQuery = useQuery({
    queryKey: ["candles", symbol, timeframe, "dashboard"],
    queryFn: () => api.getCandles(symbol, timeframe, 120),
    refetchInterval: 60000,
  });

  // Load persisted chat history on mount
  const chatHistoryQuery = useQuery({
    queryKey: ["chat-history", threadId],
    queryFn: () => api.getChat(threadId),
    // Only run if we have a threadId saved from before
    enabled: !!threadId,
    staleTime: Infinity, // Don't auto-refetch; only reload on demand
  });

  // Automated AI Agent Scan Cycle Mutation
  const scanCycleMutation = useMutation({
    mutationFn: () => {
      setAiScanStatus("observing");
      return api.runAgentCycle();
    },
    onSuccess: (data) => {
      setAiScanStatus("completed");
      const best = data.signals.find((s) => s.direction !== "neutral") || data.signals[0];
      if (best) {
        setAiLatestSummary(
          `AI scanned ${data.scanned_pairs_count} pairs. Top opportunity: ${best.symbol} ${best.direction.toUpperCase()} (${best.confidence_pct}% confidence). Stop-Loss: ${best.stop_loss ?? "Auto"}, Take-Profit: ${best.take_profit ?? "Auto"}.`
        );
      }
      setTimeout(() => setAiScanStatus("idle"), 4000);
    },
    onError: () => {
      setAiScanStatus("idle");
    },
  });

  // Chat Mutation
  const chatMutation = useMutation({
    mutationFn: (textToSend?: string) => {
      const promptText = textToSend || message;
      return api.chat({ message: promptText, symbol, timeframe, threadId });
    },
    onSuccess: (payload) => {
      const newThreadId = payload.threadId;
      setThreadId(newThreadId);
      if (newThreadId) {
        localStorage.setItem("tradeflow_thread_id", newThreadId);
      }
      // Invalidate history cache so it picks up the latest messages
      void queryClient.invalidateQueries({ queryKey: ["chat-history", newThreadId] });
      setMessage("");
    },
  });

  // New Chat handler — deletes current thread and resets UI
  const handleNewChat = async () => {
    if (threadId) {
      try { await api.newChat(threadId); } catch { /* ignore */ }
    }
    localStorage.removeItem("tradeflow_thread_id");
    setThreadId(undefined);
    chatMutation.reset();
    void queryClient.removeQueries({ queryKey: ["chat-history"] });
  };

  // Auto-scroll chat to bottom on new messages
  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chatMutation.data, chatHistoryQuery.data]);

  const account = accountQuery.data;
  const pairs = pairsQuery.data ?? [];
  const positions = positionsQuery.data ?? [];
  const signals = signalsQuery.data ?? [];
  const candles = candlesQuery.data ?? [];
  const unrealizedPnl = account?.totalUnrealizedPnl ?? 0;

  const handleQuickCommand = (prompt: string) => {
    setMessage(prompt);
    chatMutation.mutate(prompt);
  };

  const handleQuickTrade = (pairSymbol: string, side: "buy" | "sell") => {
    setSymbol(pairSymbol);
    setSelectedTradeSymbol(pairSymbol);
    setSelectedTradeSide(side);
    setActiveTab("order-desk");
  };

  return (
    <div className="space-y-6">
      {/* 1. TOP HERO: AI AGENT AUTOPILOT & STATUS CENTER */}
      <section className="relative overflow-hidden rounded-3xl border border-cyan-500/30 bg-gradient-to-r from-slate-950 via-cyan-950/20 to-slate-950 p-6 backdrop-blur shadow-2xl shadow-cyan-950/20">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <span className="flex h-3 w-3 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500" />
              </span>
              <span className="text-xs font-bold uppercase tracking-[0.25em] text-cyan-400">
                {account?.broker === "mt5" ? "Exness MT5 Gateway • Active" : "Alpaca Trading Engine • Active"}
              </span>
              <span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
                {account?.broker === "mt5"
                  ? `Exness Demo ($${(account?.balance ?? 500).toFixed(2)})`
                  : account?.mode === "live"
                  ? "Live Real Money"
                  : "Paper Money ($26.9k)"}
              </span>
            </div>

            <h1 className="text-2xl font-black text-slate-100 sm:text-3xl">
              Welcome to TradeFlow AI
            </h1>
            <p className="max-w-2xl text-xs sm:text-sm text-slate-300 leading-relaxed">
              Your AI agent continuously evaluates 10 forex pairs using technical confluence (RSI, MACD, EMAs, ATR) and strictly enforces server-side risk limits before submitting any orders to {account?.broker === "mt5" ? "Exness MetaTrader 5" : "Alpaca"}.
            </p>
          </div>

          {/* 1-Click Scan Button */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            <button
              type="button"
              disabled={scanCycleMutation.isPending}
              onClick={() => scanCycleMutation.mutate()}
              className="inline-flex items-center justify-center gap-2.5 rounded-2xl bg-gradient-to-r from-cyan-400 to-blue-500 px-5 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-cyan-500/25 hover:from-cyan-300 hover:to-blue-400 transition-all duration-200 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${scanCycleMutation.isPending ? "animate-spin" : ""}`} />
              {scanCycleMutation.isPending ? "AI is Scanning Markets..." : "Run AI Scan Cycle Now"}
            </button>
          </div>
        </div>

        {/* Live Step Progress when Scanning */}
        {scanCycleMutation.isPending && (
          <div className="mt-4 rounded-2xl border border-cyan-500/30 bg-cyan-950/40 p-4 text-xs text-cyan-200 flex items-center gap-3 animate-pulse">
            <Cpu className="h-4 w-4 text-cyan-400" />
            <span>
              <strong>AI Agent in Action [{aiScanStatus}]:</strong> Querying {account?.broker === "mt5" ? "Exness MT5" : "Alpaca"} price feeds → Computing RSI(14), MACD(12,26,9), EMA(20,50,200), ATR(14) → Verifying 2% risk limits...
            </span>
          </div>
        )}

        {/* Latest summary notification */}
        {aiLatestSummary && !scanCycleMutation.isPending && (
          <div className="mt-4 rounded-2xl border border-emerald-500/30 bg-emerald-950/30 p-3.5 text-xs text-emerald-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
              <span>{aiLatestSummary}</span>
            </div>
            <button
              type="button"
              onClick={() => setAiLatestSummary(null)}
              className="text-slate-400 hover:text-slate-200 text-xs ml-2"
            >
              Dismiss
            </button>
          </div>
        )}
      </section>

      {/* 2. LIVE METRIC CARDS */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label={account?.broker === "mt5" ? "Exness Account Equity" : "Alpaca Account Equity"}
          value={`$${(account?.equity ?? 500).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          tone="positive"
        />
        <MetricCard
          label="Available Balance"
          value={`$${(account?.balance ?? account?.cash ?? 500).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
        <MetricCard
          label={account?.broker === "mt5" ? "Leverage / Free Margin" : "Buying Power (Margin)"}
          value={account?.broker === "mt5" ? `1:${account?.leverage ?? 2000} · $${(account?.marginFree ?? 500).toFixed(0)}` : `$${(account?.buying_power ?? 107645).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
        />
        <MetricCard
          label="Active Positions P&L"
          value={`${unrealizedPnl >= 0 ? "+" : ""}$${unrealizedPnl.toFixed(2)} (${positions.length} open)`}
          tone={unrealizedPnl >= 0 ? "positive" : "warning"}
        />
      </div>

      {/* 3. "WHERE TO START" QUICK-ACTION COMMAND CARDS */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Compass className="h-4 w-4 text-cyan-400" />
            <h3 className="font-bold text-slate-100 text-sm sm:text-base">
              Where to Start: One-Click AI Commands
            </h3>
          </div>
          <span className="text-xs text-slate-400">
            Click any button below to instruct the AI instantly
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {QUICK_COMMANDS.map((cmd) => {
            const Icon = cmd.icon;
            return (
              <button
                key={cmd.id}
                type="button"
                onClick={() => handleQuickCommand(cmd.prompt)}
                className="group relative flex flex-col justify-between rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 text-left transition-all duration-200 hover:border-cyan-500/50 hover:bg-slate-900/80 hover:shadow-lg hover:shadow-cyan-950/20"
              >
                <div>
                  <div className="mb-2.5 inline-flex rounded-xl bg-cyan-500/10 p-2 text-cyan-400 border border-cyan-500/20 group-hover:scale-105 transition-transform">
                    <Icon className="h-4 w-4" />
                  </div>
                  <h4 className="font-semibold text-slate-100 text-sm group-hover:text-cyan-300 transition-colors">
                    {cmd.title}
                  </h4>
                  <p className="mt-1 text-xs text-slate-400 leading-relaxed">
                    {cmd.desc}
                  </p>
                </div>
                <div className="mt-3 flex items-center gap-1 text-[11px] font-semibold text-cyan-400">
                  <span>Run Command</span>
                  <ChevronRight className="h-3 w-3 group-hover:translate-x-0.5 transition-transform" />
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* INSTITUTIONAL EDGE RADAR (PHASE 2: ECONOMIC SHIELD, MTF CONFLUENCE, SESSION LIQUIDITY) */}
      <InstitutionalEdgeRadar symbol={symbol} />

      {/* 4. MAIN WORKSPACE: COPILOT CONVERSATION & LIVE TRADING DESK */}
      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <div className="space-y-6">
          {/* TAB SWITCHER: AI Copilot Chat vs Manual Order Panel */}
          <div className="flex items-center gap-2 border-b border-slate-800/80 pb-2">
            <button
              type="button"
              onClick={() => setActiveTab("ai-copilot")}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition-all ${
                activeTab === "ai-copilot"
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 shadow"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Bot className="h-4 w-4" />
              AI Copilot & Strategy Chat
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("order-desk")}
              className={`flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold transition-all ${
                activeTab === "order-desk"
                  ? "bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 shadow"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Zap className="h-4 w-4" />
              Direct Order Desk & Risk Meter
            </button>
          </div>

          {activeTab === "ai-copilot" ? (
            /* Dedicated AI Copilot Interactive Box */
            <section className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur flex flex-col justify-between min-h-[460px]">
              <div>
                <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-cyan-400" />
                    <h3 className="font-bold text-slate-100 text-sm">
                      Interactive AI Trader (Pair: {symbol} · {timeframe})
                    </h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full font-bold">
                      {account?.broker === "mt5" ? "Exness MT5 Live" : "Alpaca REST API"}
                    </span>
                    <button
                      type="button"
                      title="Start a new conversation"
                      onClick={() => void handleNewChat()}
                      className="flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/60 px-2.5 py-1 text-[10px] font-bold text-slate-400 hover:border-cyan-500/50 hover:text-cyan-300 transition-all"
                    >
                      <MessageSquarePlus className="h-3.5 w-3.5" />
                      New Chat
                    </button>
                  </div>
                </div>

                {/* Conversation Thread */}
                {/* Prefer live mutation messages; fall back to persisted history from backend */}
                {((): React.ReactNode => {
                  const liveMessages = chatMutation.data?.messages ?? [];
                  const historyMessages = chatHistoryQuery.data?.messages ?? [];
                  const displayMessages = liveMessages.length > 0 ? liveMessages : historyMessages;
                  return (
                    <div ref={chatScrollRef} className="mt-4 space-y-3 max-h-[380px] overflow-y-auto pr-1">
                      {displayMessages.length > 0 ? (
                        displayMessages.map((entry) => (
                          <div
                            key={entry.id}
                            className={`rounded-2xl p-4 text-xs leading-relaxed ${
                              entry.role === "user"
                                ? "bg-cyan-950/40 border border-cyan-800/40 text-cyan-100 ml-6"
                                : entry.role === "tool"
                                ? "bg-slate-900/40 border border-slate-800/60 text-slate-400 text-[11px]"
                                : "bg-slate-900/80 border border-slate-800 text-slate-100 mr-4"
                            }`}
                          >
                            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5 flex items-center gap-1.5">
                              {entry.role === "user" ? (
                                "You"
                              ) : entry.role === "tool" ? (
                                "Market & Alpaca Context Engine"
                              ) : (
                                <>
                                  <Bot className="h-3 w-3 text-cyan-400 inline" /> TradeFlow AI
                                </>
                              )}
                            </p>
                            {entry.role === "assistant" ? (
                              <MarkdownRenderer content={entry.content} />
                            ) : (
                              <p className="whitespace-pre-wrap">{entry.content}</p>
                            )}
                          </div>
                        ))
                      ) : (
                        <div className="rounded-2xl border border-dashed border-slate-800 p-8 text-center text-slate-400">
                          <Bot className="h-8 w-8 mx-auto text-slate-600 mb-2" />
                          <p className="font-semibold text-slate-200 text-sm">How to prompt your AI:</p>
                          <ul className="mt-2 text-xs space-y-1.5 text-slate-400 max-w-md mx-auto text-left list-disc list-inside">
                             <li>Click any <strong>One-Click Command</strong> card above to start immediately.</li>
                             <li>Ask for analysis: <em>&quot;Analyse EUR/USD&quot;</em> or <em>&quot;What is BTC/USD doing right now?&quot;</em></li>
                             <li>Execute a trade: <em>&quot;Buy 0.01 lot EUR/USD&quot;</em> or <em>&quot;Buy 0.01 ETH/USD&quot;</em>.</li>
                             <li>Close positions: <em>&quot;Close BTC/USD&quot;</em> or <em>&quot;Close all positions&quot;</em>.</li>
                             <li>Check risk: <em>&quot;Audit my account and risk limits&quot;</em>.</li>
                           </ul>
                        </div>
                      )}

                      {chatMutation.isPending && (
                        <div className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-3 text-xs text-cyan-300 flex items-center gap-2">
                          <RefreshCw className="h-3.5 w-3.5 animate-spin text-cyan-400" />
                          TradeFlow AI is evaluating market data and formulating analysis...
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>


              {/* Input Area */}
              <div className="mt-4 pt-3 border-t border-slate-800/60">
                <div className="relative flex items-center">
                  <input
                    type="text"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey && message.trim()) {
                        e.preventDefault();
                        chatMutation.mutate(message);
                      }
                    }}
                    placeholder={`Ask AI: 'Analyse ${symbol}' or 'Buy 0.01 lot ${symbol}' or 'Close all positions' ...`}
                    className="w-full rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 pr-12 text-xs text-slate-100 outline-none focus:border-cyan-500"
                  />
                  <button
                    type="button"
                    disabled={chatMutation.isPending || !message.trim()}
                    onClick={() => chatMutation.mutate(message)}
                    className="absolute right-2 p-2 rounded-lg bg-cyan-500 text-slate-950 hover:bg-cyan-400 transition-colors disabled:opacity-40"
                  >
                    <Send className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </section>
          ) : (
            /* Order Form Panel */
            <OrderFormPanel
              initialSymbol={selectedTradeSymbol || symbol}
              initialSide={selectedTradeSide}
              onOrderSuccess={() => {
                setSelectedTradeSymbol(null);
                setActiveTab("ai-copilot");
              }}
            />
          )}

          {/* Active Open Positions Table */}
          <PositionsTable positions={positions} isLoading={positionsQuery.isLoading} />

          {/* Candlestick Chart for the active pair */}
          <section className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-4">
              <div className="flex items-center gap-2">
                <BarChart2 className="h-4 w-4 text-cyan-400" />
                <h3 className="font-bold text-slate-100 text-sm">
                  {symbol} · {timeframe} Live Chart
                </h3>
              </div>
              <span className="text-[11px] text-slate-400 font-mono">
                {candles.length} bars
              </span>
            </div>
            <CandlestickChart data={candles} />
          </section>

          {/* Trade Audit Journal */}
          <TradeJournalTable />
        </div>

        {/* RIGHT COLUMN: REAL-TIME CURRENCY WATCHLIST & SIGNALS */}
        <div className="space-y-6">
          {/* Live Currency Grid */}
          <div className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-3">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-cyan-400" />
                <h3 className="font-bold text-slate-100 text-sm">Watchlist — Forex &amp; Crypto</h3>
              </div>
              <span className="text-[11px] text-slate-400 font-mono">
                {pairs.length} Pairs
              </span>
            </div>

            <div className="space-y-2.5 max-h-[340px] overflow-y-auto pr-1">
              {pairs.slice(0, 8).map((pair) => {
                const isSelected = pair.symbol === symbol;
                const isJpy = pair.symbol.includes("JPY");
                const decimals = isJpy ? 3 : 5;

                return (
                  <div
                    key={pair.symbol}
                    onClick={() => setSymbol(pair.symbol)}
                    className={`flex items-center justify-between rounded-xl border p-2.5 text-xs cursor-pointer transition-all ${
                      isSelected
                        ? "border-cyan-500/60 bg-cyan-950/30"
                        : "border-slate-800/70 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/70"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-100">{pair.symbol}</span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        {pair.quote.spread_pips.toFixed(1)} pips
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="font-mono text-slate-300 font-medium">
                        {pair.quote.mid.toFixed(decimals)}
                      </span>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleQuickTrade(pair.symbol, "sell");
                          }}
                          className="rounded px-2 py-0.5 text-[10px] font-bold uppercase text-rose-300 bg-rose-500/10 border border-rose-500/20 hover:bg-rose-500/20"
                        >
                          S
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleQuickTrade(pair.symbol, "buy");
                          }}
                          className="rounded px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-300 bg-emerald-500/10 border border-emerald-500/20 hover:bg-emerald-500/20"
                        >
                          B
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* AI Strategy Signals Stream */}
          <div className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-3">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-cyan-400" />
                <h3 className="font-bold text-slate-100 text-sm">AI Opportunity Stream</h3>
              </div>
              <span className="text-[11px] text-cyan-400 font-semibold font-mono">
                {signals.length} Signals
              </span>
            </div>

            <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
              {signals.map((sig) => {
                const isLong = sig.direction === "long";
                const isShort = sig.direction === "short";

                return (
                  <div
                    key={sig.id}
                    onClick={() => setSymbol(sig.symbol)}
                    className="rounded-xl border border-slate-800/70 bg-slate-900/50 p-3 text-xs hover:border-slate-700 transition-all cursor-pointer"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-slate-100">{sig.symbol}</span>
                        <span
                          className={`rounded px-1.5 py-0.2 text-[9px] font-bold uppercase ${
                            isLong
                              ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                              : isShort
                              ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                              : "bg-slate-700/30 text-slate-400"
                          }`}
                        >
                          {sig.direction.toUpperCase()}
                        </span>
                      </div>
                      <span className="font-mono text-xs font-bold text-slate-200">
                        {sig.confidencePct}% Conf.
                      </span>
                    </div>

                    <p className="mt-1.5 text-[11px] text-slate-400 line-clamp-2">
                      {sig.reasoning}
                    </p>
                  </div>
                );
              })}

              {signals.length === 0 && (
                <div className="p-6 text-center text-xs text-slate-500">
                  No signals generated yet. Click &quot;Run AI Scan Cycle Now&quot; above!
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
