import React, { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  TrendingDown,
  TrendingUp,
  Activity,
  Zap,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Minus,
  RefreshCw,
  Bell,
  BellOff,
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PairResult {
  symbol: string;
  alert: "TRADEABLE" | "PENDING" | "CONFLICTED" | "RANGING" | "ERROR";
  macro_bias: "BULLISH" | "BEARISH" | "CONSOLIDATION";
  h4_rsi: number;
  h4_ema200: number;
  h1_direction: string;
  h1_rsi: number;
  m15_direction: string;
  m15_rsi: number;
  confluence_quality: string;
  composite_score: number;
  is_aligned: boolean;
  suggested_side: "buy" | "sell" | null;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  rr_ratio: number;
  rejection_reason: string | null;
  bid: number | null;
  ask: number | null;
  spread: number | null;
  ok: boolean;
  error?: string;
}

interface ScanResult {
  scanned_count: number;
  opportunities_count: number;
  pending_count: number;
  conflicted_count: number;
  has_opportunities: boolean;
  results: PairResult[];
  opportunities: PairResult[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const API_BASE = "/api";

const SCAN_INTERVAL_MS = 60_000; // 60 seconds

function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(" ");
}

function alertConfig(alert: PairResult["alert"]) {
  switch (alert) {
    case "TRADEABLE":
      return {
        label: "TRADE NOW",
        dot: "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.8)]",
        badge: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40",
        card: "border-emerald-500/40 bg-emerald-500/5",
        glow: true,
      };
    case "PENDING":
      return {
        label: "WATCH",
        dot: "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]",
        badge: "bg-amber-500/20 text-amber-300 border border-amber-500/40",
        card: "border-amber-500/30 bg-amber-500/5",
        glow: false,
      };
    case "CONFLICTED":
      return {
        label: "HOLD",
        dot: "bg-rose-400",
        badge: "bg-rose-500/20 text-rose-300 border border-rose-500/40",
        card: "border-slate-700 bg-slate-900/50",
        glow: false,
      };
    case "RANGING":
      return {
        label: "RANGE",
        dot: "bg-slate-500",
        badge: "bg-slate-700/50 text-slate-400 border border-slate-700",
        card: "border-slate-800 bg-slate-900/30",
        glow: false,
      };
    default:
      return {
        label: "ERROR",
        dot: "bg-slate-600",
        badge: "bg-slate-800 text-slate-500 border border-slate-700",
        card: "border-slate-800 bg-slate-900/20",
        glow: false,
      };
  }
}

function biasIcon(bias: string, dir: string) {
  const isUp = bias === "BULLISH" || dir === "long";
  const isDown = bias === "BEARISH" || dir === "short";
  if (isUp) return <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />;
  if (isDown) return <TrendingDown className="w-3.5 h-3.5 text-rose-400" />;
  return <Minus className="w-3.5 h-3.5 text-slate-500" />;
}

function rsiColor(rsi: number) {
  if (rsi >= 70) return "text-rose-400";
  if (rsi <= 30) return "text-emerald-400";
  return "text-slate-300";
}

function formatPrice(p: number | null, sym: string): string {
  if (p === null || p === undefined) return "—";
  if (sym.startsWith("BTC")) return p.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (sym.startsWith("ETH") || sym.startsWith("SOL")) return p.toFixed(2);
  return p.toFixed(5);
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function PairCard({ pair, index }: { pair: PairResult; index: number }) {
  const cfg = alertConfig(pair.alert);
  const [expanded, setExpanded] = useState(pair.alert === "TRADEABLE");

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
      className={cn(
        "rounded-2xl border transition-all overflow-hidden",
        cfg.card,
        cfg.glow && "shadow-lg shadow-emerald-500/10"
      )}
    >
      {/* Header row */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center gap-4 p-4 text-left hover:bg-white/5 transition-colors"
      >
        {/* Pulse dot */}
        <span
          className={cn(
            "w-2.5 h-2.5 rounded-full flex-shrink-0",
            cfg.dot,
            pair.alert === "TRADEABLE" && "animate-pulse"
          )}
        />

        {/* Symbol */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold text-slate-100">{pair.symbol}</span>
            <span className={cn("text-[10px] font-black uppercase px-2 py-0.5 rounded-full", cfg.badge)}>
              {cfg.label}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-0.5 text-[11px] text-slate-500">
            <span className="flex items-center gap-1">
              {biasIcon(pair.macro_bias, "")}
              4H: {pair.macro_bias}
            </span>
            <span className="flex items-center gap-1">
              {biasIcon("", pair.h1_direction)}
              1H: {pair.h1_direction?.toUpperCase()}
            </span>
            <span className="flex items-center gap-1">
              {biasIcon("", pair.m15_direction)}
              15M: {pair.m15_direction?.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Score ring */}
        <div className="flex-shrink-0 text-right">
          <div
            className={cn(
              "text-lg font-black",
              pair.composite_score >= 70
                ? "text-emerald-400"
                : pair.composite_score >= 50
                ? "text-amber-400"
                : "text-slate-500"
            )}
          >
            {pair.composite_score?.toFixed(0)}
          </div>
          <div className="text-[9px] uppercase text-slate-600 tracking-widest">Score</div>
        </div>
      </button>

      {/* Expanded detail */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
              {/* RSI row */}
              <div className="grid grid-cols-3 gap-2 text-center">
                {[
                  { label: "4H RSI", val: pair.h4_rsi },
                  { label: "1H RSI", val: pair.h1_rsi },
                  { label: "15M RSI", val: pair.m15_rsi },
                ].map((item) => (
                  <div key={item.label} className="bg-slate-950/60 rounded-xl p-2">
                    <div className={cn("text-base font-bold", rsiColor(item.val))}>
                      {item.val?.toFixed(1)}
                    </div>
                    <div className="text-[9px] text-slate-600 uppercase tracking-wider mt-0.5">
                      {item.label}
                    </div>
                  </div>
                ))}
              </div>

              {/* EMA200 */}
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-500">4H EMA200</span>
                <span className="text-slate-300 font-mono">{formatPrice(pair.h4_ema200, pair.symbol)}</span>
              </div>

              {/* Quote */}
              {pair.bid !== null && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">Bid / Ask</span>
                  <span className="text-slate-300 font-mono">
                    {formatPrice(pair.bid, pair.symbol)} / {formatPrice(pair.ask, pair.symbol)}
                  </span>
                </div>
              )}

              {/* Trade setup if aligned */}
              {pair.is_aligned && pair.entry_price !== null && (
                <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-3 space-y-2">
                  <div className="flex items-center gap-2 text-emerald-400 text-xs font-bold uppercase tracking-wider">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Trade Setup — {pair.suggested_side?.toUpperCase()}
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center text-xs">
                    <div>
                      <div className="text-slate-300 font-mono">{formatPrice(pair.entry_price, pair.symbol)}</div>
                      <div className="text-[9px] text-slate-600 uppercase">Entry</div>
                    </div>
                    <div>
                      <div className="text-rose-400 font-mono">{formatPrice(pair.stop_loss, pair.symbol)}</div>
                      <div className="text-[9px] text-slate-600 uppercase">Stop</div>
                    </div>
                    <div>
                      <div className="text-emerald-400 font-mono">{formatPrice(pair.take_profit, pair.symbol)}</div>
                      <div className="text-[9px] text-slate-600 uppercase">Target</div>
                    </div>
                  </div>
                  <div className="text-center text-[10px] text-slate-400">
                    R:R Ratio — <span className="text-emerald-400 font-bold">{pair.rr_ratio?.toFixed(1)}R</span>
                  </div>
                </div>
              )}

              {/* Rejection / waiting note */}
              {!pair.is_aligned && pair.rejection_reason && (
                <div className="flex items-start gap-2 text-xs text-slate-500 bg-slate-950/40 rounded-xl p-3">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500/70 flex-shrink-0 mt-0.5" />
                  <span>{pair.rejection_reason}</span>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export function AlignmentScanner() {
  const [scanData, setScanData] = useState<ScanResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastScanTime, setLastScanTime] = useState<Date | null>(null);
  const [countdown, setCountdown] = useState(SCAN_INTERVAL_MS / 1000);
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [prevOpportunities, setPrevOpportunities] = useState<string[]>([]);
  const [newAlerts, setNewAlerts] = useState<string[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);

  // ── Alert sound ─────────────────────────────────────────────────────────
  function playAlert() {
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      audioCtxRef.current = ctx;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = "sine";
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.3);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.4);
    } catch (_) {}
  }

  // ── Fetch scan ──────────────────────────────────────────────────────────
  const runScan = useCallback(async () => {
    setLoading(true);
    setCountdown(SCAN_INTERVAL_MS / 1000);
    try {
      const resp = await fetch(`${API_BASE}/market/alignment-scan`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data: ScanResult = await resp.json();
      setScanData(data);
      setLastScanTime(new Date());

      // Detect newly tradeable pairs
      const currentOpps = data.opportunities.map((o) => o.symbol);
      const newlyAligned = currentOpps.filter((s) => !prevOpportunities.includes(s));
      if (newlyAligned.length > 0) {
        setNewAlerts(newlyAligned);
        if (alertsEnabled) playAlert();
        // Auto-clear alerts after 8s
        setTimeout(() => setNewAlerts([]), 8000);
      }
      setPrevOpportunities(currentOpps);
    } catch (err) {
      console.error("Alignment scan error:", err);
    } finally {
      setLoading(false);
    }
  }, [prevOpportunities, alertsEnabled]);

  // ── Polling ─────────────────────────────────────────────────────────────
  useEffect(() => {
    runScan();

    timerRef.current = setInterval(runScan, SCAN_INTERVAL_MS);

    countRef.current = setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : SCAN_INTERVAL_MS / 1000));
    }, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (countRef.current) clearInterval(countRef.current);
    };
  }, []);

  // ── New alert banner ─────────────────────────────────────────────────────
  const AlertBanner = () => (
    <AnimatePresence>
      {newAlerts.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: -20, scale: 0.95 }}
          className="fixed top-20 right-8 z-50 bg-emerald-950 border border-emerald-400/60 rounded-2xl p-4 shadow-2xl shadow-emerald-500/30 flex items-center gap-3 max-w-xs"
        >
          <div className="w-9 h-9 bg-emerald-500/20 rounded-xl flex items-center justify-center flex-shrink-0">
            <Zap className="w-5 h-5 text-emerald-400 animate-pulse" />
          </div>
          <div>
            <p className="text-sm font-bold text-emerald-300">
              {newAlerts.length === 1
                ? `${newAlerts[0]} is now tradeable!`
                : `${newAlerts.length} pairs are now tradeable!`}
            </p>
            <p className="text-[10px] text-emerald-500/70 mt-0.5">All timeframes aligned ✓</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <>
      <AlertBanner />

      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-2xl font-bold flex items-center gap-3">
              <div className="w-8 h-8 bg-indigo-600/20 border border-indigo-500/30 rounded-xl flex items-center justify-center">
                <Activity className="w-4 h-4 text-indigo-400" />
              </div>
              Alignment Scanner
            </h2>
            <p className="text-sm text-slate-500 mt-0.5">
              Real-time multi-timeframe confluence across all crypto pairs
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Alert toggle */}
            <button
              onClick={() => setAlertsEnabled((v) => !v)}
              className={cn(
                "p-2.5 rounded-xl border transition-all",
                alertsEnabled
                  ? "bg-indigo-600/10 border-indigo-500/30 text-indigo-400"
                  : "bg-slate-900 border-slate-700 text-slate-500"
              )}
              title={alertsEnabled ? "Mute alerts" : "Enable alerts"}
            >
              {alertsEnabled ? <Bell className="w-4 h-4" /> : <BellOff className="w-4 h-4" />}
            </button>

            {/* Manual refresh */}
            <button
              onClick={runScan}
              disabled={loading}
              className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-4 py-2.5 rounded-xl text-sm font-semibold transition-all shadow-lg shadow-indigo-500/20"
            >
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
              {loading ? "Scanning…" : "Scan Now"}
            </button>
          </div>
        </div>

        {/* Stat bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            {
              label: "Tradeable",
              value: scanData?.opportunities_count ?? "—",
              color: "text-emerald-400",
              bg: "bg-emerald-500/5 border-emerald-500/20",
            },
            {
              label: "Pending",
              value: scanData?.pending_count ?? "—",
              color: "text-amber-400",
              bg: "bg-amber-500/5 border-amber-500/20",
            },
            {
              label: "Conflicted",
              value: scanData?.conflicted_count ?? "—",
              color: "text-rose-400",
              bg: "bg-rose-500/5 border-rose-500/20",
            },
            {
              label: "Scanned",
              value: scanData?.scanned_count ?? "—",
              color: "text-indigo-400",
              bg: "bg-indigo-500/5 border-indigo-500/20",
            },
          ].map((s) => (
            <div key={s.label} className={cn("rounded-xl border p-4 text-center", s.bg)}>
              <div className={cn("text-2xl font-black", s.color)}>{s.value}</div>
              <div className="text-[10px] uppercase tracking-widest text-slate-600 mt-1">{s.label}</div>
            </div>
          ))}
        </div>

        {/* Next scan countdown */}
        <div className="flex items-center gap-2 text-xs text-slate-600">
          <Clock className="w-3.5 h-3.5" />
          {lastScanTime ? (
            <>
              Last scan: {lastScanTime.toLocaleTimeString()} — Next refresh in{" "}
              <span className="text-slate-400 font-mono font-bold">{countdown}s</span>
            </>
          ) : (
            "Initializing scanner…"
          )}
        </div>

        {/* Loading skeleton */}
        {loading && !scanData && (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div
                key={i}
                className="h-16 rounded-2xl bg-slate-900 border border-slate-800 animate-pulse"
              />
            ))}
          </div>
        )}

        {/* No opportunity state */}
        {scanData && !loading && scanData.opportunities_count === 0 && (
          <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-8 text-center">
            <div className="w-14 h-14 bg-slate-800 rounded-full mx-auto flex items-center justify-center mb-4">
              <Clock className="w-7 h-7 text-slate-600" />
            </div>
            <h3 className="text-lg font-bold text-slate-300 mb-1">Standing By</h3>
            <p className="text-sm text-slate-500 max-w-md mx-auto">
              No pairs are aligned across all 3 timeframes right now. The scanner will alert you
              automatically when a high-probability setup appears. Capital preserved. ✓
            </p>
          </div>
        )}

        {/* Results list */}
        {scanData && (
          <div className="space-y-3">
            {scanData.results.map((pair, idx) => (
              <PairCard key={pair.symbol} pair={pair} index={idx} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}
