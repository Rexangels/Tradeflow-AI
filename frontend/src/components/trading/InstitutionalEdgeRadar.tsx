import React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Calendar,
  Clock,
  Globe,
  Layers,
  ShieldAlert,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";

import { api } from "../../lib/api";

interface InstitutionalEdgeRadarProps {
  symbol: string;
}

export const InstitutionalEdgeRadar: React.FC<InstitutionalEdgeRadarProps> = ({ symbol }) => {
  // 1. Session Query
  const sessionsQuery = useQuery({
    queryKey: ["trading-sessions"],
    queryFn: api.getTradingSessions,
    refetchInterval: 15000,
  });

  // 2. Economic Calendar & News Shield Query
  const calendarQuery = useQuery({
    queryKey: ["economic-calendar", symbol],
    queryFn: () => api.getEconomicCalendar(symbol),
    refetchInterval: 30000,
  });

  // 3. Multi-Timeframe Top-Down Confluence Query
  const mtfQuery = useQuery({
    queryKey: ["mtf-confluence", symbol],
    queryFn: () => api.getMultiTimeframeConfluence(symbol),
    refetchInterval: 10000,
  });

  const session = sessionsQuery.data;
  const calendar = calendarQuery.data;
  const shield = calendar?.shield_status;
  const mtf = mtfQuery.data;

  const isBlockedByNews = shield?.is_blocked ?? false;
  const isRollover = session?.is_rollover ?? false;

  return (
    <section className="rounded-2xl border border-slate-800/80 bg-slate-900/50 p-5 backdrop-blur space-y-4">
      {/* Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="rounded-xl bg-cyan-500/10 p-2 text-cyan-400 border border-cyan-500/20">
            <Layers className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-100 text-sm">
                Institutional Edge Radar & Risk Filters
              </h3>
              <span className="rounded-full bg-cyan-500/10 border border-cyan-500/30 px-2 py-0.5 text-[10px] font-extrabold text-cyan-300">
                Phase 2 Core Engine
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Top-Down H4/H1/M15 Confluence · Economic News Shield · Institutional Session Timing for <span className="font-semibold text-slate-200">{symbol}</span>
            </p>
          </div>
        </div>

        {/* Global Market Status Badge */}
        <div className="flex items-center gap-2">
          {session ? (
            <div
              className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-bold border ${
                session.favorable_for_trading
                  ? "bg-emerald-950/40 border-emerald-500/30 text-emerald-300"
                  : isRollover
                  ? "bg-rose-950/40 border-rose-500/30 text-rose-300"
                  : "bg-amber-950/40 border-amber-500/30 text-amber-300"
              }`}
            >
              <Globe className="h-3.5 w-3.5" />
              <span>{session.primary_session}</span>
              <span className="opacity-60 text-[10px]">({session.current_utc_time})</span>
            </div>
          ) : (
            <div className="h-7 w-28 animate-pulse rounded-xl bg-slate-800/50" />
          )}
        </div>
      </div>

      {/* Grid of 3 Main Shields & Confluences */}
      <div className="grid gap-4 md:grid-cols-3">
        {/* PANEL 1: ECONOMIC NEWS SHIELD */}
        <div
          className={`rounded-xl border p-4 flex flex-col justify-between transition-all ${
            isBlockedByNews
              ? "bg-rose-950/30 border-rose-500/40 shadow-lg shadow-rose-950/30"
              : "bg-slate-950/60 border-slate-800/80"
          }`}
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                {isBlockedByNews ? (
                  <ShieldAlert className="h-4 w-4 text-rose-400 animate-pulse" />
                ) : (
                  <ShieldCheck className="h-4 w-4 text-emerald-400" />
                )}
                <span className="text-xs font-bold text-slate-200">Economic News Shield</span>
              </div>
              <span
                className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border ${
                  isBlockedByNews
                    ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                    : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                }`}
              >
                {isBlockedByNews ? "PAUSED (RED FOLDER)" : "SHIELD CLEAR"}
              </span>
            </div>

            {isBlockedByNews ? (
              <div className="space-y-1.5 mt-2">
                <p className="text-xs text-rose-200 font-medium">
                  {shield?.reason ?? "High-impact economic release imminent. New entries blocked."}
                </p>
                <p className="text-[11px] text-rose-300/80">
                  Protects capital from slippage, spread blowouts, and erratic spikes.
                </p>
              </div>
            ) : (
              <p className="text-xs text-slate-400 mt-2">
                No high-impact releases affecting {symbol} within the -30m / +15m danger window. Normal algorithmic entries permitted.
              </p>
            )}
          </div>

          {/* Upcoming Event Countdown */}
          {calendar?.events && calendar.events.length > 0 && calendar.events[0] && (
            <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3 text-cyan-400" />
                Next: {calendar.events[0].name.slice(0, 22)}...
              </span>
              <span className="font-bold text-cyan-300">
                in {calendar.events[0].minutes_away}m
              </span>
            </div>
          )}
        </div>

        {/* PANEL 2: INSTITUTIONAL SESSION & LIQUIDITY */}
        <div
          className={`rounded-xl border p-4 flex flex-col justify-between transition-all ${
            isRollover
              ? "bg-rose-950/30 border-rose-500/40"
              : "bg-slate-950/60 border-slate-800/80"
          }`}
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-cyan-400" />
                <span className="text-xs font-bold text-slate-200">Session Liquidity</span>
              </div>
              <span
                className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border ${
                  session?.liquidity_rating === "OPTIMAL"
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                    : session?.liquidity_rating === "HIGH"
                    ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/30"
                    : session?.liquidity_rating === "HAZARDOUS"
                    ? "bg-rose-500/20 text-rose-300 border-rose-500/30"
                    : "bg-amber-500/20 text-amber-300 border-amber-500/30"
                }`}
              >
                {session?.liquidity_rating ?? "CHECKING"} ({session?.liquidity_score ?? 0}%)
              </span>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed mt-2">
              {session?.advice ?? "Evaluating global session interbank spreads and volatility..."}
            </p>
          </div>

          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
            <span>Active Centers:</span>
            <span className="font-bold text-slate-200">
              {session?.active_sessions?.join(" · ") || "Evaluating"}
            </span>
          </div>
        </div>

        {/* PANEL 3: TOP-DOWN MTF CONFLUENCE RADAR */}
        <div
          className={`rounded-xl border p-4 flex flex-col justify-between transition-all ${
            mtf?.is_aligned
              ? "bg-emerald-950/20 border-emerald-500/40 shadow-lg shadow-emerald-950/20"
              : mtf?.confluence_quality === "CONFLICTED"
              ? "bg-amber-950/20 border-amber-500/30"
              : "bg-slate-950/60 border-slate-800/80"
          }`}
        >
          <div>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-amber-400" />
                <span className="text-xs font-bold text-slate-200">Top-Down Confluence</span>
              </div>
              <span
                className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded-full border ${
                  mtf?.is_aligned
                    ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                    : mtf?.confluence_quality === "CONFLICTED"
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                    : "bg-slate-800 text-slate-400 border-slate-700"
                }`}
              >
                {mtf?.confluence_quality ?? "ANALYZING"} · {mtf?.composite_score ?? 0}%
              </span>
            </div>

            {/* Timeframe Pillars: 4H -> 1H -> 15M */}
            <div className="grid grid-cols-3 gap-2 mt-3 text-center">
              {/* 4H Macro */}
              <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-2">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">4H Bias</span>
                <span
                  className={`text-xs font-black inline-flex items-center gap-0.5 mt-1 ${
                    mtf?.macro_bias_4h === "BULLISH"
                      ? "text-emerald-400"
                      : mtf?.macro_bias_4h === "BEARISH"
                      ? "text-rose-400"
                      : "text-amber-400"
                  }`}
                >
                  {mtf?.macro_bias_4h === "BULLISH" ? (
                    <TrendingUp className="h-3 w-3" />
                  ) : mtf?.macro_bias_4h === "BEARISH" ? (
                    <TrendingDown className="h-3 w-3" />
                  ) : null}
                  {mtf?.macro_bias_4h?.slice(0, 4) ?? "---"}
                </span>
              </div>

              {/* 1H Structure */}
              <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-2">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">1H Momentum</span>
                <span
                  className={`text-xs font-black inline-flex items-center gap-0.5 mt-1 ${
                    mtf?.h1.direction === "long"
                      ? "text-emerald-400"
                      : mtf?.h1.direction === "short"
                      ? "text-rose-400"
                      : "text-slate-300"
                  }`}
                >
                  {mtf?.h1.direction?.toUpperCase() ?? "---"}
                </span>
              </div>

              {/* 15M Trigger */}
              <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-2">
                <span className="text-[10px] uppercase font-bold text-slate-400 block">15M Trigger</span>
                <span
                  className={`text-xs font-black inline-flex items-center gap-0.5 mt-1 ${
                    mtf?.m15.direction === "long"
                      ? "text-emerald-400"
                      : mtf?.m15.direction === "short"
                      ? "text-rose-400"
                      : "text-slate-300"
                  }`}
                >
                  {mtf?.m15.direction?.toUpperCase() ?? "---"}
                </span>
              </div>
            </div>

            {/* Verdict Explanation */}
            <p className="mt-2.5 text-[11px] text-slate-300 leading-tight">
              {mtf?.rejection_reason ?? (
                mtf?.is_aligned ? (
                  <span className="text-emerald-300 font-medium">
                    Strong 3-Timeframe confluence aligned for {mtf.suggested_side?.toUpperCase()} entry (1.5R+ min target).
                  </span>
                ) : (
                  "Waiting for multi-timeframe signal alignment."
                )
              )}
            </p>
          </div>

          <div className="mt-3 pt-2.5 border-t border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
            <span>Suggested Action:</span>
            <span
              className={`font-black uppercase ${
                mtf?.suggested_side === "buy"
                  ? "text-emerald-400"
                  : mtf?.suggested_side === "sell"
                  ? "text-rose-400"
                  : "text-slate-400"
              }`}
            >
              {mtf?.suggested_side ? `${mtf.suggested_side} Setup` : "Stand Aside"}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
};
