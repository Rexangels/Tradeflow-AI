import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";

import type { Candle, ExecutedTrade } from "../shared";

const DEFAULT_VISIBLE_CANDLES = 48;

export function CandlestickChart({
  data,
  trades = [],
  height = 360,
  playbackIndex,
  selectedTradeId,
  onTradeSelect,
}: {
  data: Candle[];
  trades?: ExecutedTrade[];
  height?: number;
  playbackIndex?: number;
  selectedTradeId?: string;
  onTradeSelect?: (trade: ExecutedTrade) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const [visibleCount, setVisibleCount] = useState(DEFAULT_VISIBLE_CANDLES);
  const [windowEnd, setWindowEnd] = useState(0);

  useEffect(() => {
    if (data.length === 0) {
      setWindowEnd(0);
      return;
    }

    setWindowEnd(data.length);
    setVisibleCount((current) => {
      if (current <= 0) {
        return Math.min(DEFAULT_VISIBLE_CANDLES, data.length);
      }
      return Math.min(current, data.length);
    });
  }, [data.length]);

  const minimumVisible = Math.min(12, Math.max(1, data.length));
  const clampedVisibleCount = data.length === 0 ? 0 : Math.min(Math.max(visibleCount, minimumVisible), data.length);
  const clampedWindowEnd = data.length === 0 ? 0 : Math.min(Math.max(windowEnd || data.length, clampedVisibleCount), data.length);
  const requestedPlaybackIndex = playbackIndex ?? (data.length > 0 ? data.length - 1 : 0);
  const clampedPlaybackIndex = data.length === 0 ? 0 : Math.min(Math.max(requestedPlaybackIndex, 0), data.length - 1);

  useEffect(() => {
    if (data.length === 0 || playbackIndex === undefined) {
      return;
    }

    if (clampedPlaybackIndex >= clampedWindowEnd) {
      setWindowEnd(Math.min(data.length, clampedPlaybackIndex + 1));
      return;
    }

    const currentWindowStart = Math.max(0, clampedWindowEnd - clampedVisibleCount);
    if (clampedPlaybackIndex < currentWindowStart) {
      setWindowEnd(Math.min(data.length, clampedPlaybackIndex + clampedVisibleCount));
    }
  }, [clampedPlaybackIndex, clampedVisibleCount, clampedWindowEnd, data.length, playbackIndex]);

  const windowStart = Math.max(0, clampedWindowEnd - clampedVisibleCount);
  const visibleEntries = useMemo(
    () => data.map((candle, index) => ({ candle, index })).slice(windowStart, clampedWindowEnd),
    [clampedWindowEnd, data, windowStart],
  );
  const visibleTradeTimes = new Set(
    visibleEntries.filter((entry) => entry.index <= clampedPlaybackIndex).map((entry) => entry.candle.time),
  );
  const visibleTrades = trades.filter((trade) => visibleTradeTimes.has(trade.time));

  useEffect(() => {
    if (!containerRef.current || !svgRef.current || visibleEntries.length === 0) {
      return;
    }

    const width = containerRef.current.clientWidth || 900;
    const margin = { top: 20, right: 24, bottom: 48, left: 60 };
    const chartWidth = width - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const x = d3
      .scaleBand()
      .domain(visibleEntries.map((entry) => entry.candle.time))
      .range([0, chartWidth])
      .padding(0.22);

    const y = d3
      .scaleLinear()
      .domain([
        d3.min(visibleEntries, (entry) => entry.candle.low)! * 0.995,
        d3.max(visibleEntries, (entry) => entry.candle.high)! * 1.005,
      ])
      .nice()
      .range([chartHeight, 0]);

    const root = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    root
      .append("g")
      .attr("transform", `translate(0,${chartHeight})`)
      .call(
        d3
          .axisBottom(x)
          .tickValues(x.domain().filter((_, index) => index % Math.max(1, Math.floor(visibleEntries.length / 6)) === 0))
          .tickFormat((value) => formatChartTime(String(value))),
      )
      .attr("color", "#64748b")
      .call((axis) => {
        axis.selectAll("text").style("font-size", "11px");
      });

    root
      .append("g")
      .call(d3.axisLeft(y).ticks(6))
      .attr("color", "#64748b")
      .call((axis) => {
        axis.selectAll("text").style("font-size", "11px");
      });

    root
      .append("g")
      .attr("opacity", 0.08)
      .call(d3.axisLeft(y).tickSize(-chartWidth).tickFormat(() => ""));

    const candles = root.selectAll(".candle").data(visibleEntries).enter().append("g").attr("class", "candle");

    candles
      .append("line")
      .attr("x1", (entry) => (x(entry.candle.time) ?? 0) + x.bandwidth() / 2)
      .attr("x2", (entry) => (x(entry.candle.time) ?? 0) + x.bandwidth() / 2)
      .attr("y1", (entry) => y(entry.candle.high))
      .attr("y2", (entry) => y(entry.candle.low))
      .attr("stroke", (entry) => (entry.candle.close >= entry.candle.open ? "#10b981" : "#f43f5e"))
      .attr("stroke-width", 1.2)
      .attr("opacity", (entry) => (entry.index <= clampedPlaybackIndex ? 1 : 0.22));

    candles
      .append("rect")
      .attr("x", (entry) => x(entry.candle.time) ?? 0)
      .attr("y", (entry) => y(Math.max(entry.candle.open, entry.candle.close)))
      .attr("width", x.bandwidth())
      .attr("height", (entry) => Math.max(2, Math.abs(y(entry.candle.open) - y(entry.candle.close))))
      .attr("rx", 2)
      .attr("fill", (entry) => (entry.candle.close >= entry.candle.open ? "#34d399" : "#fb7185"))
      .attr("opacity", (entry) => (entry.index <= clampedPlaybackIndex ? 0.95 : 0.16));

    root
      .selectAll(".trade")
      .data(visibleTrades)
      .enter()
      .append("path")
      .attr("d", (trade) => d3.symbol().type(d3.symbolTriangle).size(trade.id === selectedTradeId ? 108 : 68)())
      .attr("transform", (trade) => {
        const xPosition = (x(trade.time) ?? 0) + x.bandwidth() / 2;
        const yPosition = trade.type === "buy" ? y(trade.price) + 12 : y(trade.price) - 12;
        const rotation = trade.type === "buy" ? 0 : 180;
        return `translate(${xPosition},${yPosition}) rotate(${rotation})`;
      })
      .attr("fill", (trade) => (trade.type === "buy" ? "#fbbf24" : "#38bdf8"))
      .attr("stroke", (trade) => (trade.id === selectedTradeId ? "#f8fafc" : "#020617"))
      .attr("stroke-width", (trade) => (trade.id === selectedTradeId ? 2.2 : 1.2))
      .style("cursor", onTradeSelect ? "pointer" : "default")
      .on("click", (_event, trade) => {
        onTradeSelect?.(trade);
      })
      .append("title")
      .text((trade) => `${trade.type.toUpperCase()} ${trade.price.toFixed(2)} | ${new Date(trade.time).toLocaleString()}`);

    const activeEntry = visibleEntries.find((entry) => entry.index === clampedPlaybackIndex);
    if (activeEntry) {
      const xPosition = (x(activeEntry.candle.time) ?? 0) + x.bandwidth() / 2;
      root
        .append("line")
        .attr("x1", xPosition)
        .attr("x2", xPosition)
        .attr("y1", 0)
        .attr("y2", chartHeight)
        .attr("stroke", "#f8fafc")
        .attr("stroke-dasharray", "4 4")
        .attr("opacity", 0.4);
    }
  }, [clampedPlaybackIndex, height, onTradeSelect, selectedTradeId, visibleEntries, visibleTrades]);

  const canZoomIn = clampedVisibleCount > minimumVisible;
  const canZoomOut = clampedVisibleCount < data.length;
  const canPanLeft = windowStart > 0;
  const canPanRight = clampedWindowEnd < data.length;

  return (
    <div ref={containerRef} className="rounded-3xl border border-slate-800 bg-slate-950/80 p-4">
      <div className="mb-4 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setWindowEnd((current) => Math.max(clampedVisibleCount, current - Math.max(1, Math.floor(clampedVisibleCount / 3))))}
            disabled={!canPanLeft}
            className="rounded-2xl border border-slate-700 bg-slate-900/80 px-3 py-2 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Pan Left
          </button>
          <button
            type="button"
            onClick={() => setWindowEnd((current) => Math.min(data.length, current + Math.max(1, Math.floor(clampedVisibleCount / 3))))}
            disabled={!canPanRight}
            className="rounded-2xl border border-slate-700 bg-slate-900/80 px-3 py-2 text-xs text-slate-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Pan Right
          </button>
          <button
            type="button"
            onClick={() => setVisibleCount((current) => Math.max(minimumVisible, Math.floor(current * 0.7)))}
            disabled={!canZoomIn}
            className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Zoom In
          </button>
          <button
            type="button"
            onClick={() => setVisibleCount((current) => Math.min(data.length, Math.ceil(current * 1.35)))}
            disabled={!canZoomOut}
            className="rounded-2xl border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-xs text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Zoom Out
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
          {[24, 48, 96, data.length].filter((count, index, list) => list.indexOf(count) === index).map((count) => (
            <button
              key={count}
              type="button"
              onClick={() => setVisibleCount(count)}
              className={`rounded-2xl border px-3 py-2 ${
                clampedVisibleCount === count
                  ? "border-slate-200 bg-slate-100 text-slate-950"
                  : "border-slate-700 bg-slate-900/80 text-slate-300"
              }`}
            >
              {count === data.length ? "All" : `${count} bars`}
            </button>
          ))}
          <span className="ml-2 rounded-2xl border border-slate-800 bg-slate-900/70 px-3 py-2">
            Showing {visibleEntries.length} of {data.length}
          </span>
        </div>
      </div>

      {data.length > clampedVisibleCount ? (
        <div className="mb-4">
          <input
            aria-label="Chart position"
            type="range"
            min={clampedVisibleCount}
            max={data.length}
            value={clampedWindowEnd}
            onChange={(event) => setWindowEnd(Number(event.target.value))}
            className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-800 accent-cyan-300"
          />
        </div>
      ) : null}

      <svg ref={svgRef} width="100%" height={height} />

      <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-slate-400">
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
          Bullish candles
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-400" />
          Bearish candles
        </span>
        {playbackIndex !== undefined ? (
          <span className="inline-flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-slate-100" />
            Playback cursor
          </span>
        ) : null}
        {onTradeSelect ? (
          <span className="inline-flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-amber-200" />
            Click a trade marker to inspect that decision
          </span>
        ) : null}
      </div>
    </div>
  );
}


function formatChartTime(value: string) {
  const date = new Date(value);
  return d3.timeFormat("%b %d %H:%M")(date);
}
