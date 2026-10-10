import { useMutation, useQuery } from "@tanstack/react-query";
import { ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { queryClient } from "../../lib/query-client";
import { POPULAR_MARKETS } from "../../lib/workspace-options";
import type { RiskAssessment } from "../../shared";

interface OrderFormPanelProps {
  initialSymbol?: string;
  initialSide?: "buy" | "sell";
  onOrderSuccess?: () => void;
}

export function OrderFormPanel({
  initialSymbol = "EUR/USD",
  initialSide = "buy",
  onOrderSuccess,
}: OrderFormPanelProps) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [side, setSide] = useState<"buy" | "sell">(initialSide);
  const [qty, setQty] = useState("1000");
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [riskAssessment, setRiskAssessment] = useState<RiskAssessment | null>(null);

  useEffect(() => {
    setSymbol(initialSymbol);
  }, [initialSymbol]);

  useEffect(() => {
    setSide(initialSide);
  }, [initialSide]);

  // Fetch live quote for the symbol to auto-populate sensible brackets
  const quoteQuery = useQuery({
    queryKey: ["forex-quote", symbol],
    queryFn: () => api.getForexQuote(symbol),
    refetchInterval: 5000,
  });

  const quote = quoteQuery.data;

  // Auto-calibrate SL & TP based on current mid quote if empty
  const handleAutoBracket = () => {
    if (!quote) return;
    const mid = quote.mid;
    const isJpy = symbol.includes("JPY");
    const pip = isJpy ? 0.01 : 0.0001;
    const decimals = isJpy ? 3 : 5;
    const defaultSlPips = 25 * pip;
    const defaultTpPips = 50 * pip; // 2.0R ratio

    if (side === "buy") {
      setStopLoss((mid - defaultSlPips).toFixed(decimals));
      setTakeProfit((mid + defaultTpPips).toFixed(decimals));
    } else {
      setStopLoss((mid + defaultSlPips).toFixed(decimals));
      setTakeProfit((mid - defaultTpPips).toFixed(decimals));
    }
  };

  // Run dry-run risk check whenever values change
  useEffect(() => {
    const parsedQty = parseFloat(qty);
    const parsedSl = parseFloat(stopLoss);
    const parsedTp = parseFloat(takeProfit);

    if (parsedQty > 0 && parsedSl > 0) {
      api
        .checkRisk({
          symbol,
          side,
          qty: parsedQty,
          current_price: quote?.mid,
          stop_loss: parsedSl,
          take_profit: parsedTp > 0 ? parsedTp : undefined,
        })
        .then((res) => setRiskAssessment(res))
        .catch(() => setRiskAssessment(null));
    } else {
      setRiskAssessment(null);
    }
  }, [symbol, side, qty, stopLoss, takeProfit, quote?.mid]);

  const orderMutation = useMutation({
    mutationFn: () =>
      api.placeTradingOrder({
        symbol,
        side,
        qty: parseFloat(qty),
        order_type: orderType,
        limit_price: limitPrice ? parseFloat(limitPrice) : undefined,
        stop_loss: stopLoss ? parseFloat(stopLoss) : undefined,
        take_profit: takeProfit ? parseFloat(takeProfit) : undefined,
        ai_reasoning: "Manual trader execution with risk validation",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trading-positions"] });
      queryClient.invalidateQueries({ queryKey: ["trading-account"] });
      queryClient.invalidateQueries({ queryKey: ["trading-orders"] });
      onOrderSuccess?.();
    },
  });

  const orderError = orderMutation.error ? (orderMutation.error as Error).message : null;

  return (
    <div className="rounded-2xl border border-slate-800/80 bg-slate-950/80 p-5 backdrop-blur">
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3.5">
        <div>
          <h3 className="font-semibold text-slate-100 text-base">Trade Execution</h3>
          <p className="text-xs text-slate-400 mt-0.5">
            Submit risk-managed bracket orders directly to Alpaca
          </p>
        </div>
        <span className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[11px] font-semibold text-cyan-300">
          Alpaca Paper
        </span>
      </div>

      <div className="mt-4 space-y-4">
        {/* Symbol & Side Selection */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Currency Pair</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-500"
            >
              {POPULAR_MARKETS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Action Side</label>
            <div className="grid grid-cols-2 gap-1.5 rounded-xl border border-slate-800 bg-slate-900 p-1">
              <button
                type="button"
                onClick={() => setSide("buy")}
                className={`rounded-lg py-1 text-xs font-semibold uppercase transition-colors ${
                  side === "buy" ? "bg-emerald-500 text-slate-950 shadow" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                BUY
              </button>
              <button
                type="button"
                onClick={() => setSide("sell")}
                className={`rounded-lg py-1 text-xs font-semibold uppercase transition-colors ${
                  side === "sell" ? "bg-rose-500 text-slate-950 shadow" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                SELL
              </button>
            </div>
          </div>
        </div>

        {/* Units Quantity & Order Type */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Position Size (Units)</label>
            <input
              type="number"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              placeholder="1000"
              className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-sm font-mono text-slate-100 outline-none focus:border-cyan-500"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Order Type</label>
            <select
              value={orderType}
              onChange={(e) => setOrderType(e.target.value as "market" | "limit")}
              className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-cyan-500"
            >
              <option value="market">Market Order</option>
              <option value="limit">Limit Order</option>
            </select>
          </div>
        </div>

        {orderType === "limit" && (
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">Limit Price</label>
            <input
              type="number"
              step="any"
              value={limitPrice}
              onChange={(e) => setLimitPrice(e.target.value)}
              placeholder={quote ? quote.mid.toString() : "1.08500"}
              className="w-full rounded-xl border border-slate-800 bg-slate-900 px-3 py-2 text-sm font-mono text-slate-100 outline-none focus:border-cyan-500"
            />
          </div>
        )}

        {/* Bracket Stop-Loss & Take-Profit */}
        <div className="rounded-xl border border-slate-800/80 bg-slate-900/50 p-3.5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
              Risk Brackets (Mandatory)
            </span>
            <button
              type="button"
              onClick={handleAutoBracket}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              <Sparkles className="h-3 w-3" />
              Auto 2.0R Bracket
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[11px] font-medium text-rose-300">Stop-Loss Price</label>
              <input
                type="number"
                step="any"
                value={stopLoss}
                onChange={(e) => setStopLoss(e.target.value)}
                placeholder="Required"
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 text-xs font-mono text-rose-200 outline-none focus:border-rose-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-[11px] font-medium text-emerald-300">Take-Profit Price</label>
              <input
                type="number"
                step="any"
                value={takeProfit}
                onChange={(e) => setTakeProfit(e.target.value)}
                placeholder="Optional / Target"
                className="w-full rounded-lg border border-slate-800 bg-slate-950 px-2.5 py-1.5 text-xs font-mono text-emerald-200 outline-none focus:border-emerald-500"
              />
            </div>
          </div>
        </div>

        {/* Live Risk Guardrail Assessment Meter */}
        {riskAssessment && (
          <div
            className={`rounded-xl border p-3 text-xs transition-all ${
              riskAssessment.approved
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : "border-rose-500/30 bg-rose-500/10 text-rose-200"
            }`}
          >
            <div className="flex items-center gap-2 font-semibold">
              {riskAssessment.approved ? (
                <>
                  <ShieldCheck className="h-4 w-4 text-emerald-400" />
                  <span>Risk Rules Passed (Approved)</span>
                </>
              ) : (
                <>
                  <ShieldAlert className="h-4 w-4 text-rose-400" />
                  <span>Risk Rule Violation</span>
                </>
              )}
            </div>
            <p className="mt-1 text-[11px] opacity-90">{riskAssessment.reason}</p>
            {riskAssessment.risk_amount_usd !== undefined && (
              <div className="mt-2 flex items-center gap-4 text-[11px] border-t border-slate-700/40 pt-1.5">
                <span>
                  Risk: <strong>${riskAssessment.risk_amount_usd}</strong> ({riskAssessment.risk_pct}%)
                </span>
                {riskAssessment.rr_ratio !== undefined && (
                  <span>
                    R:R: <strong>{riskAssessment.rr_ratio}R</strong>
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {orderError && (
          <div className="rounded-xl border border-rose-500/40 bg-rose-500/15 p-3 text-xs text-rose-200">
            {orderError}
          </div>
        )}

        {/* Execute Button */}
        <button
          type="button"
          disabled={orderMutation.isPending || (riskAssessment !== null && !riskAssessment.approved)}
          onClick={() => orderMutation.mutate()}
          className={`w-full rounded-xl py-3 text-sm font-semibold transition-all duration-200 shadow-md ${
            side === "buy"
              ? "bg-emerald-500 hover:bg-emerald-400 text-slate-950 shadow-emerald-500/20 disabled:opacity-50"
              : "bg-rose-500 hover:bg-rose-400 text-slate-950 shadow-rose-500/20 disabled:opacity-50"
          }`}
        >
          {orderMutation.isPending
            ? "Routing to Alpaca..."
            : `Execute ${side.toUpperCase()} ${symbol}`}
        </button>
      </div>
    </div>
  );
}
