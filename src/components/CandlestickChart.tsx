import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { Candle, Trade } from '../types';

interface CandlestickChartProps {
  data: Candle[];
  trades?: Trade[];
  height?: number;
  width?: number;
  playbackIndex?: number;
}

export function CandlestickChart({ data, trades = [], height = 400, width = 800, playbackIndex }: CandlestickChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!data || data.length === 0 || !svgRef.current || !containerRef.current) return;

    const chartData = playbackIndex !== undefined ? data.slice(0, playbackIndex + 1) : data;
    const chartTrades = playbackIndex !== undefined ? trades.filter(t => new Date(t.time) <= new Date(chartData[chartData.length - 1].time)) : trades;

    const margin = { top: 20, right: 50, bottom: 30, left: 50 };
    const chartWidth = (containerRef.current.clientWidth || width) - margin.left - margin.right;
    const chartHeight = height - margin.top - margin.bottom;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const x = d3.scaleBand()
      .domain(chartData.map(d => d.time))
      .range([0, chartWidth])
      .padding(0.2);

    const y = d3.scaleLinear()
      .domain([
        d3.min(chartData, d => d.low)! * 0.99,
        d3.max(chartData, d => d.high)! * 1.01
      ])
      .range([chartHeight, 0]);

    const g = svg.append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    // Axes
    g.append("g")
      .attr("transform", `translate(0,${chartHeight})`)
      .call(d3.axisBottom(x).tickValues(x.domain().filter((d, i) => !(i % Math.floor(chartData.length / 6)))))
      .attr("color", "#475569");

    g.append("g")
      .call(d3.axisLeft(y))
      .attr("color", "#475569");

    // Grid lines
    g.append("g")
      .attr("class", "grid")
      .attr("opacity", 0.1)
      .call(d3.axisLeft(y).tickSize(-chartWidth).tickFormat(() => ""));

    // Candlesticks
    const candles = g.selectAll(".candle")
      .data(chartData)
      .enter().append("g")
      .attr("class", "candle");

    // Wicks
    candles.append("line")
      .attr("x1", d => x(d.time)! + x.bandwidth() / 2)
      .attr("x2", d => x(d.time)! + x.bandwidth() / 2)
      .attr("y1", d => y(d.high))
      .attr("y2", d => y(d.low))
      .attr("stroke", d => d.close > d.open ? "#10b981" : "#ef4444")
      .attr("stroke-width", 1);

    // Bodies
    candles.append("rect")
      .attr("x", d => x(d.time)!)
      .attr("y", d => y(Math.max(d.open, d.close)))
      .attr("width", x.bandwidth())
      .attr("height", d => Math.max(1, Math.abs(y(d.open) - y(d.close))))
      .attr("fill", d => d.close > d.open ? "#10b981" : "#ef4444")
      .attr("rx", 1);

    // Trades
    const tradeMarkers = g.selectAll(".trade")
      .data(chartTrades)
      .enter().append("g")
      .attr("class", "trade");

    tradeMarkers.append("path")
      .attr("d", d => d.type === 'buy' ? d3.symbol().type(d3.symbolTriangle).size(64)() : d3.symbol().type(d3.symbolTriangle).size(64)())
      .attr("transform", d => {
        const candle = chartData.find(c => c.time === d.time);
        if (!candle) return "";
        const yPos = d.type === 'buy' ? y(candle.low) + 15 : y(candle.high) - 15;
        const rotate = d.type === 'buy' ? 0 : 180;
        return `translate(${x(d.time)! + x.bandwidth() / 2},${yPos}) rotate(${rotate})`;
      })
      .attr("fill", d => d.type === 'buy' ? "#10b981" : "#ef4444")
      .attr("stroke", "#fff")
      .attr("stroke-width", 1);

  }, [data, trades, height, width, playbackIndex]);

  return (
    <div ref={containerRef} className="w-full bg-slate-950/50 rounded-2xl border border-slate-800 p-4 overflow-hidden">
      <svg ref={svgRef} width="100%" height={height} className="overflow-visible" />
    </div>
  );
}
