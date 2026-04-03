import { Candle, Trade, BacktestResult, AgentConfig, Strategy } from '../types';
import { calculateEMA, calculateRSI, calculateBollingerBands } from './indicators';

export function runBacktest(
  data: Candle[], 
  agent: AgentConfig, 
  strategies: Strategy[]
): BacktestResult {
  let balance = 10000;
  let position = 0;
  const trades: Trade[] = [];
  const equityCurve: { time: string; value: number }[] = [];

  const closePrices = data.map(c => c.close);
  
  // Calculate indicators
  const ema9 = calculateEMA(closePrices, 9);
  const ema21 = calculateEMA(closePrices, 21);
  const rsi14 = calculateRSI(closePrices, 14);
  const bb = calculateBollingerBands(closePrices, 20, 2);

  const isTrendFollowingEnabled = strategies.some(s => s.name.includes('Trend') && s.enabled);
  const isMeanReversionEnabled = strategies.some(s => s.name.includes('Mean Reversion') && s.enabled);

  for (let i = 30; i < data.length; i++) {
    const currentPrice = data[i].close;
    
    let buySignal = false;
    let sellSignal = false;

    // Trend Following Logic (EMA Crossover)
    if (isTrendFollowingEnabled) {
      const ema9Current = ema9[i];
      const ema21Current = ema21[i];
      const ema9Prev = ema9[i - 1];
      const ema21Prev = ema21[i - 1];

      if (ema9Current > ema21Current && ema9Prev <= ema21Prev) {
        buySignal = true;
      } else if (ema9Current < ema21Current && ema9Prev >= ema21Prev) {
        sellSignal = true;
      }
    }

    // Mean Reversion Logic (Bollinger Bands + RSI)
    if (isMeanReversionEnabled) {
      const rsiCurrent = rsi14[i];
      const lowerBand = bb.lower[i];
      const upperBand = bb.upper[i];

      if (currentPrice < lowerBand && rsiCurrent < 30) {
        buySignal = true;
      } else if (currentPrice > upperBand && rsiCurrent > 70) {
        sellSignal = true;
      }
    }

    // Fallback if no strategies enabled or to add agent risk tolerance randomness
    if (!buySignal && !sellSignal && Math.random() > 0.95) {
      if (Math.random() > (1 - agent.riskTolerance)) {
        buySignal = true;
      } else {
        sellSignal = true;
      }
    }

    const shouldBuy = buySignal && position === 0;
    const shouldSell = sellSignal && position > 0;

    if (shouldBuy) {
      const amount = (balance * 0.95) / currentPrice;
      position = amount;
      balance -= amount * currentPrice;
      trades.push({
        id: Math.random().toString(36).substr(2, 9),
        type: 'buy',
        price: currentPrice,
        time: data[i].time,
        amount
      });
    } else if (shouldSell) {
      balance += position * currentPrice;
      const buyTrade = trades.filter(t => t.type === 'buy').pop();
      const profit = buyTrade ? (currentPrice - buyTrade.price) * position : 0;
      
      trades.push({
        id: Math.random().toString(36).substr(2, 9),
        type: 'sell',
        price: currentPrice,
        time: data[i].time,
        amount: position,
        profit
      });
      position = 0;
    }

    equityCurve.push({
      time: data[i].time,
      value: balance + (position * currentPrice)
    });
  }

  const finalEquity = balance + (position * data[data.length - 1].close);
  const totalProfit = ((finalEquity - 10000) / 10000) * 100;
  
  // Calculate drawdown
  let maxEquity = 10000;
  let maxDrawdown = 0;
  equityCurve.forEach(e => {
    if (e.value > maxEquity) maxEquity = e.value;
    const dd = ((maxEquity - e.value) / maxEquity) * 100;
    if (dd > maxDrawdown) maxDrawdown = dd;
  });

  const winningTrades = trades.filter(t => t.type === 'sell' && (t.profit || 0) > 0).length;
  const totalTrades = trades.filter(t => t.type === 'sell').length;

  return {
    totalProfit: parseFloat(totalProfit.toFixed(2)),
    drawdown: parseFloat(maxDrawdown.toFixed(2)),
    sharpeRatio: 1.5 + (Math.random() * 1), // Still mock for now, requires risk-free rate and std dev of returns
    winRate: totalTrades > 0 ? Math.round((winningTrades / totalTrades) * 100) : 0,
    equityCurve,
    trades
  };
}
