import { Candle, Trade, BacktestResult, AgentConfig, Strategy } from '../types';

export function runBacktest(
  data: Candle[], 
  agent: AgentConfig, 
  strategies: Strategy[]
): BacktestResult {
  let balance = 10000;
  let position = 0;
  const trades: Trade[] = [];
  const equityCurve: { time: string; value: number }[] = [];

  // Simple heuristic/mock RL logic for the MVP
  // In a real app, this would call an RL model inference
  for (let i = 20; i < data.length; i++) {
    const currentPrice = data[i].close;
    const prevPrice = data[i-1].close;
    
    // Heuristic: Trend following + random "RL" exploration
    const isTrendingUp = currentPrice > prevPrice;
    const shouldBuy = isTrendingUp && Math.random() > (1 - agent.riskTolerance) && position === 0;
    const shouldSell = !isTrendingUp && position > 0;

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
    sharpeRatio: 1.5 + (Math.random() * 1), // Mock
    winRate: totalTrades > 0 ? Math.round((winningTrades / totalTrades) * 100) : 0,
    equityCurve,
    trades
  };
}
