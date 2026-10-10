# TradeFlow AI: Institutional Upgrade Roadmap

## 1. Executive Summary & Current State

TradeFlow AI is an automated, AI-augmented trading platform. 
Through rigorous testing on live Alpaca accounts and algorithmic analysis, the following core conclusions were established:

1. **Broker & Asset Reality**:
   - Alpaca Paper API supports US Equities (Stocks/ETFs) and Crypto, but does **not** support spot Forex order routing (HTTP 422 asset not found).
   - For live trading from Nigeria, traditional US brokerage wire funding is unviable. The optimal live trading path is an **MT5 Cent Account (Exness / HFM)** where a **$15 USD deposit converts into 1,500 USC (Cent balance)**, allowing 0.01 cent lots risking only $0.03 per trade (0.2% risk) to adhere strictly to mathematical risk management.

2. **Algorithm Reality**:
   - LLMs (e.g., Gemini) provide high-value reasoning, trade triage, risk management, and trailing stop optimization, but do not predict price spikes independently.
   - Lagging indicators (RSI, MACD, Moving Averages) on a single timeframe produce false signals during choppy sessions and market consolidations.
   - To achieve genuine algorithmic edge (*Alpha*), the system requires:
     - **Economic News Shield** (halting trades around Red-Folder events).
     - **Top-Down Multi-Timeframe Confluence** (H4 Trend Bias ➔ H1 Key Levels ➔ M15 Trigger).
     - **Session Liquidity Filters** (trading exclusively during London & New York volatility).

---

## 2. Phased Architecture Roadmap

```
┌────────────────────────────────────────────────────────────────────────┐
│                   TradeFlow AI Evolution Roadmap                       │
└────────────────────────────────────────────────────────────────────────┘

 [Phase 1: Foundation (COMPLETED ✅)]
   ├── Alpaca REST Client & Order Execution Pipeline
   ├── Institutional Risk Guardrails (Max 2% Risk, Mandatory Stops, 1.5R Min)
   ├── Dynamic Trailing Stop Loss & Zero-Risk Breakeven Shield
   ├── Clickable Position Detail & AI Guardian Management Modal
   └── AI Copilot Chat Interface with Intent Handling (Gemini 2.5 Flash)

 [Phase 2: Alpha Edge & Strategy Engine (IN PROGRESS 🚀)]
   ├── 1. Economic News Shield (High-Impact Red-Folder Event Filter)
   ├── 2. Top-Down Multi-Timeframe Confluence Engine (H4 / H1 / M15)
   ├── 3. Global Trading Session & Liquidity Filter (London & New York Windows)
   └── 4. Integrated Signal Quality Score (0-100% Weighted Confluence)

 [Phase 3: Broker Abstraction & MT5 Cent Adapter]
   ├── Modular Broker Gateway Interface
   ├── MetaTrader 5 (MT5) REST / Cloud Bridge (Exness / HFM / IC Markets)
   ├── Cent Account (USC) Sizing & Fractional Lot Scaling (0.01 Cent Lot = $0.001/pip)
   └── Deriv WebSocket / REST Gateway for Synthetic & Forex Options

 [Phase 4: Automated Backtesting & Real-Time Benchmark Engine]
   ├── Historical Multi-Timeframe Strategy Stress-Tester
   ├── Sharpe Ratio, Maximum Drawdown (MDD), and Profit Factor Analytics
   └── Forward Walk Testing & Automated Performance Journal
```

---

## 3. Detailed Specifications for Phase 2 Implementation

### Feature 2.1: Economic News Shield (`economic_calendar.py`)
- **Objective**: Prevent entering new positions when major macro data (NFP, CPI, FOMC, Rate Decisions) causes violent spread widening and slippage.
- **Rules**:
  - Filter by affected currency (USD, EUR, GBP, AUD, JPY).
  - High Impact (Red Folder): Block trades **30 minutes before** and **15 minutes after** the release.
  - Active Protection: Automatically tighten stops to Breakeven for existing open positions before high-impact events.

### Feature 2.2: Multi-Timeframe Top-Down Confluence (`multi_timeframe.py`)
- **Objective**: Eliminate counter-trend trades by verifying market structure across three distinct time horizons.
- **Hierarchy**:
  1. **Higher Timeframe (H4 / 4-Hour)**: Trend Bias. Price vs 200 EMA and market structure (Higher Highs vs Lower Lows).
  2. **Intermediate Timeframe (H1 / 1-Hour)**: Momentum & Dynamic Support/Resistance (EMA 20/50, RSI 40-60 baseline).
  3. **Lower Timeframe (M15 / 15-Minute)**: Execution Trigger (Breakout or pullback entry with minimal stop distance).
- **Enforcement**: If H4 is Bearish, **M15 Buy signals are strictly prohibited**.

### Feature 2.3: Session Timing & Liquidity Engine (`session_filter.py`)
- **Objective**: Restrict entries to high-volume hours when institutional liquidity ensures tight spreads.
- **Sessions**:
  - **London Session**: 07:00 – 11:00 UTC (High Trend Initiation).
  - **New York / London Overlap**: 12:00 – 16:00 UTC (Peak Global Volume).
  - **Asian Session**: 00:00 – 06:00 UTC (Low Volatility; flagged as Ranging / Reduced Sizing).

---

## 4. Verification & Benchmark Protocol

Following code implementation:
1. **Unit & Integration Suite**: Verify risk manager blocks trades during simulated news windows and counter-trend signals.
2. **Backtest Benchmarking**: Compare single-timeframe strategies against multi-timeframe + news shield strategies.
3. **Frontend Diagnostics**: Validate that the UI displays real-time News Shield status, active trading session, and multi-timeframe ratings.
