export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type Timeframe = '1m' | '5m' | '1h' | '1d';

export type DataSource = 'Yahoo Finance' | 'Binance' | 'Alpha Vantage' | 'Polygon.io';

export interface AgentConfig {
  id: string;
  name: string;
  type: 'pretrained' | 'custom';
  rewardStyle: 'aggressive' | 'conservative' | 'balanced';
  riskTolerance: number; // 0 to 1
  holdingBehavior: 'short-term' | 'long-term';
}

export interface Strategy {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

export interface BacktestResult {
  totalProfit: number;
  drawdown: number;
  sharpeRatio: number;
  winRate: number;
  equityCurve: { time: string; value: number }[];
  trades: Trade[];
}

export interface Trade {
  id: string;
  type: 'buy' | 'sell';
  price: number;
  time: string;
  amount: number;
  profit?: number;
}
