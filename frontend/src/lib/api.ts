import type {
  AdminSession,
  AgentConfig,
  AiChatResponse,
  AISignalItem,
  BacktestRequest,
  BacktestResult,
  Candle,
  ForexPair,
  ForexQuote,
  PaperAccount,
  PaperOrder,
  RiskAssessment,
  RiskRules,
  SettingsResponse,
  TradeLogItem,
  TradingAccount,
  TradingPosition,
} from "../shared";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:4000";

async function extractErrorMessage(response: Response): Promise<string> {
  const body = await response.text();
  if (!body) {
    return `Request failed: ${response.status}`;
  }

  try {
    const payload = JSON.parse(body) as { detail?: string | string[] } | Record<string, unknown>;
    const detail = payload.detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail) && typeof detail[0] === "string") {
      return detail[0];
    }
  } catch {
    const titleMatch = body.match(/<title>(.*?)<\/title>/i);
    const htmlError = titleMatch?.[1]?.replace(/\s+/g, " ").trim();
    if (htmlError) {
      return `Server error: ${htmlError}`;
    }
    return body;
  }

  return body;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/api/v1${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {}),
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

export interface PositionDetailsResponse {
  success: boolean;
  symbol: string;
  display_symbol: string;
  asset_class: string;
  side: "long" | "short";
  qty: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  breakeven_price: number;
  is_protected: boolean;
  risk_alert: string | null;
  active_protection: {
    trailing_stop: {
      id: string;
      trail_percent: number;
      trail_price: number;
      stop_price: number;
      hwm: number;
      qty: number;
    } | null;
    stop_loss: {
      id: string;
      stop_price: number;
      qty: number;
    } | null;
    take_profit: {
      id: string;
      limit_price: number;
      qty: number;
    } | null;
  };
  trailing_presets: {
    conservative_3pct: { pct: number; stop_price: number; guaranteed_pnl: number };
    balanced_5pct: { pct: number; stop_price: number; guaranteed_pnl: number };
    swing_8pct: { pct: number; stop_price: number; guaranteed_pnl: number };
  };
  error?: string;
}

export interface BrokerGatewayResponse {
  activeBroker: "alpaca" | "mt5";
  brokers: {
    alpaca: {
      name: string;
      mode: string;
      connected: boolean;
      equity: number;
      supportedAssets: string[];
    };
    mt5: {
      name: string;
      login: string;
      server: string;
      currency: string;
      isCentAccount: boolean;
      balance: number;
      connected: boolean;
      statusNote?: string | null;
      supportedAssets: string[];
    };
  };
}

export const api = {
  health: () => request<{ status: string; service: string }>("/health"),
  getSession: () => request<AdminSession>("/admin/session"),
  login: (email: string, password: string) =>
    request<AdminSession>("/admin/session", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () =>
    request<AdminSession>("/admin/session", {
      method: "DELETE",
    }),
  getAgents: () => request<AgentConfig[]>("/agents"),
  createAgent: (payload: Omit<AgentConfig, "id" | "createdAt" | "updatedAt">) =>
    request<AgentConfig>("/agents", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateAgent: (id: string, payload: Omit<AgentConfig, "id" | "createdAt" | "updatedAt">) =>
    request<AgentConfig>(`/agents/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getCandles: (symbol: string, timeframe: string, limit = 300, forceRefresh = false) =>
    request<Candle[]>(`/market-data/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=${limit}&forceRefresh=${forceRefresh}`),
  getMarketDataStatus: (symbol: string, timeframe: string) =>
    request<MarketDataStatusResponse>(`/market-data/status?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`),
  getBacktests: () => request<BacktestResult[]>("/backtests"),
  runBacktest: (payload: BacktestRequest) =>
    request<BacktestResult>("/backtests", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getPaperAccount: () => request<PaperAccount>("/paper-trading/account"),
  placePaperOrder: (payload: Record<string, unknown>) =>
    request<{ sessionId: string; order: PaperOrder; account: PaperAccount }>("/paper-trading/orders", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getPaperSession: (sessionId: string) => request<Record<string, unknown>>(`/paper-trading/sessions/${sessionId}`),
  getSettings: () => request<SettingsResponse & { dashboard: Record<string, unknown> }>("/settings"),
  chat: (payload: Record<string, unknown>) =>
    request<AiChatResponse>("/ai/chat", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getChat: (threadId?: string) =>
    request<AiChatResponse>(
      `/ai/chat${threadId ? `?threadId=${encodeURIComponent(threadId)}` : ""}`,
    ),
  newChat: (threadId?: string) =>
    request<{ threadId: null; messages: [] }>(
      `/ai/chat${threadId ? `?threadId=${encodeURIComponent(threadId)}` : ""}`,
      { method: "DELETE" },
    ),

  // Forex & Alpaca Live Trading
  getForexPairs: () => request<ForexPair[]>("/forex/pairs"),
  updateForexPair: (symbol: string, payload: Partial<ForexPair>) =>
    request<ForexPair>(`/forex/pairs/${encodeURIComponent(symbol)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  getForexQuote: (symbol: string) => request<ForexQuote>(`/forex/quote/${encodeURIComponent(symbol)}`),
  getActiveBroker: () => request<BrokerGatewayResponse>("/trading/broker"),
  setActiveBroker: (broker: "alpaca" | "mt5") =>
    request<{ activeBroker: string; status: string }>("/trading/broker", {
      method: "POST",
      body: JSON.stringify({ broker }),
    }),
  getTradingAccount: () => request<TradingAccount>("/trading/account"),
  getTradingPositions: () => request<TradingPosition[]>("/trading/positions"),
  getTradingPositionDetails: (symbol: string) =>
    request<PositionDetailsResponse>(`/trading/positions/${encodeURIComponent(symbol)}`),
  protectTradingPosition: (
    symbol: string,
    payload: {
      protect_type: "trailing_stop" | "stop_loss" | "breakeven" | "bracket";
      trail_percent?: number;
      stop_loss?: number;
      take_profit?: number;
    },
  ) =>
    request<{
      success: boolean;
      symbol: string;
      protection_type: string;
      message: string;
      placed_orders: Array<{ type: string; id: string; stop_price?: number; trail_percent?: number; limit_price?: number }>;
      error?: string;
    }>(`/trading/positions/${encodeURIComponent(symbol)}`, {
      method: "POST",
      body: JSON.stringify({ action: "protect", ...payload }),
    }),
  getTradingPositionAiAdvice: (symbol: string) =>
    request<{
      success: boolean;
      symbol: string;
      ai_advice: string;
      suggested_trail_percent: number;
      suggested_stop_loss: number;
      suggested_take_profit: number;
      breakeven_price: number;
      details: PositionDetailsResponse;
      error?: string;
    }>(`/trading/positions/${encodeURIComponent(symbol)}`, {
      method: "POST",
      body: JSON.stringify({ action: "ai_advise" }),
    }),
  closeTradingPositionPartial: (
    symbol: string,
    payload: { percentage?: number; qty?: number },
  ) =>
    request<{
      success: boolean;
      symbol: string;
      closed_qty: number;
      remaining_qty: number;
      error?: string;
    }>(`/trading/positions/${encodeURIComponent(symbol)}`, {
      method: "POST",
      body: JSON.stringify({ action: "close_partial", ...payload }),
    }),
  closeTradingPosition: (symbol: string, qty?: number) =>
    request<{ success: boolean; symbol: string; closed_at_price?: number; error?: string }>(
      `/trading/positions/${encodeURIComponent(symbol)}${qty ? `?qty=${qty}` : ""}`,
      { method: "DELETE" },
    ),
  getTradingOrders: (limit = 50) => request<TradeLogItem[]>(`/trading/orders?limit=${limit}`),
  placeTradingOrder: (payload: {
    symbol: string;
    side: "buy" | "sell";
    qty: number;
    order_type?: string;
    limit_price?: number;
    stop_loss?: number;
    take_profit?: number;
    ai_reasoning?: string;
    bypass_risk?: boolean;
  }) =>
    request<{ success: boolean; order_id: string; trade_log_id: string; entry_price: number; error?: string }>(
      "/trading/orders",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
    ),
  cancelTradingOrder: (orderId: string) =>
    request<{ success: boolean; order_id: string; error?: string }>(`/trading/orders/${orderId}`, {
      method: "DELETE",
    }),
  getRiskRules: () => request<RiskRules>("/risk/rules"),
  updateRiskRules: (rules: Record<string, unknown>) =>
    request<{ status: string; rules: RiskRules }>("/risk/rules", {
      method: "PUT",
      body: JSON.stringify(rules),
    }),
  checkRisk: (payload: {
    symbol: string;
    side: string;
    qty: number;
    current_price?: number;
    stop_loss?: number;
    take_profit?: number;
  }) =>
    request<RiskAssessment>("/risk/check", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  runAgentCycle: (payload?: { agent_id?: string; symbol?: string; auto_trade?: boolean }) =>
    request<{
      timestamp: string;
      account: TradingAccount;
      scanned_pairs_count: number;
      signals: Array<{
        symbol: string;
        direction: string;
        confidence: number;
        confidence_pct: number;
        suggested_side: string;
        current_price: number;
        stop_loss: number | null;
        take_profit: number | null;
        rr_ratio: number;
        reasons: string[];
      }>;
      executed_trades: unknown[];
    }>("/ai/agent-cycle", {
      method: "POST",
      body: JSON.stringify(payload ?? {}),
    }),
  getSignals: () => request<AISignalItem[]>("/signals"),
  getEconomicCalendar: (symbol?: string) =>
    request<EconomicCalendarResponse>(`/market/economic-calendar${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`),
  getTradingSessions: () => request<TradingSessionsResponse>("/market/sessions"),
  getMultiTimeframeConfluence: (symbol: string) =>
    request<MTFConfluenceResponse>(`/market/mtf-confluence/${encodeURIComponent(symbol)}`),
};

export interface MarketDataStatusResponse {
  available: boolean;
  symbol: string;
  timeframe: string;
  source?: string;
  isRealData?: boolean;
  latestBarTime?: string | null;
  checkedAt?: string;
  error?: string;
}

export interface EconomicCalendarResponse {
  events: Array<{
    id: string;
    currency: string;
    name: string;
    impact: string;
    scheduled_time: string;
    minutes_away: number;
    forecast?: string;
    previous?: string;
  }>;
  shield_status?: {
    symbol: string;
    is_blocked: boolean;
    reason: string | null;
    event?: any;
  } | null;
}

export interface TradingSessionsResponse {
  current_utc_time: string;
  current_hour_utc: number;
  primary_session: string;
  active_sessions: string[];
  liquidity_rating: string;
  liquidity_score: number;
  favorable_for_trading: boolean;
  advice: string;
  is_london_ny_overlap: boolean;
  is_rollover: boolean;
}

export interface MTFConfluenceResponse {
  symbol: string;
  normalized_symbol: string;
  macro_bias_4h: "BULLISH" | "BEARISH" | "CONSOLIDATION";
  h4: { direction: string; confidence_pct: number; price: number; ema200: number; ema50: number; rsi: number };
  h1: { direction: string; confidence_pct: number; rsi: number; macd_histogram: number };
  m15: { direction: string; confidence_pct: number; rsi: number; atr_pips: number };
  is_aligned: boolean;
  confluence_quality: string;
  composite_score: number;
  rejection_reason?: string | null;
  suggested_side?: "buy" | "sell" | null;
  entry_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  rr_ratio: number;
}
