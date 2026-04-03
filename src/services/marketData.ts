import { Candle, Timeframe } from '../types';

const INTERVAL_MAP: Record<Timeframe, string> = {
  '1m': '1m',
  '5m': '5m',
  '1h': '1h',
  '1d': '1d',
};

export async function fetchBinanceData(symbol: string, timeframe: Timeframe, limit: number = 500): Promise<Candle[]> {
  const formattedSymbol = symbol.replace('/', '').toUpperCase();
  const interval = INTERVAL_MAP[timeframe];
  const url = `https://api.binance.com/api/v3/klines?symbol=${formattedSymbol}&interval=${interval}&limit=${limit}`;

  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to fetch data');
    const data = await response.json();

    return data.map((d: any) => ({
      time: new Date(d[0]).toISOString(),
      open: parseFloat(d[1]),
      high: parseFloat(d[2]),
      low: parseFloat(d[3]),
      close: parseFloat(d[4]),
      volume: parseFloat(d[5]),
    }));
  } catch (error) {
    console.error('Error fetching Binance data:', error);
    return [];
  }
}
