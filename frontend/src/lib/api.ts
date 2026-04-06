import type {
  AdminSession,
  AgentConfig,
  AiChatResponse,
  BacktestRequest,
  BacktestResult,
  Candle,
  PaperAccount,
  PaperOrder,
  SettingsResponse,
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
};
