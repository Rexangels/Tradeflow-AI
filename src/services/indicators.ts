export function calculateSMA(data: number[], period: number): number[] {
  const sma: number[] = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      sma.push(NaN);
      continue;
    }
    let sum = 0;
    for (let j = 0; j < period; j++) {
      sum += data[i - j];
    }
    sma.push(sum / period);
  }
  return sma;
}

export function calculateEMA(data: number[], period: number): number[] {
  const ema: number[] = [];
  const multiplier = 2 / (period + 1);
  
  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      ema.push(data[0]);
    } else {
      ema.push((data[i] - ema[i - 1]) * multiplier + ema[i - 1]);
    }
  }
  return ema;
}

export function calculateRSI(data: number[], period: number = 14): number[] {
  const rsi: number[] = [];
  let gains = 0;
  let losses = 0;

  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      rsi.push(NaN);
      continue;
    }

    const diff = data[i] - data[i - 1];
    if (i <= period) {
      if (diff > 0) gains += diff;
      else losses -= diff;
      
      if (i === period) {
        const avgGain = gains / period;
        const avgLoss = losses / period;
        const rs = avgGain / (avgLoss === 0 ? 1 : avgLoss);
        rsi.push(100 - (100 / (1 + rs)));
      } else {
        rsi.push(NaN);
      }
    } else {
      const prevAvgGain = gains;
      const prevAvgLoss = losses;
      
      const currentGain = diff > 0 ? diff : 0;
      const currentLoss = diff < 0 ? -diff : 0;

      gains = (prevAvgGain * (period - 1) + currentGain) / period;
      losses = (prevAvgLoss * (period - 1) + currentLoss) / period;

      const rs = gains / (losses === 0 ? 1 : losses);
      rsi.push(100 - (100 / (1 + rs)));
    }
  }
  return rsi;
}

export function calculateMACD(data: number[], fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
  const fastEMA = calculateEMA(data, fastPeriod);
  const slowEMA = calculateEMA(data, slowPeriod);
  
  const macdLine = fastEMA.map((fast, i) => fast - slowEMA[i]);
  
  // Calculate signal line (EMA of MACD line)
  // We need to filter out NaNs for the signal line calculation if there are any
  const validMacdLine = macdLine.filter(val => !isNaN(val));
  const signalLineValid = calculateEMA(validMacdLine, signalPeriod);
  
  const signalLine = new Array(data.length - validMacdLine.length).fill(NaN).concat(signalLineValid);
  
  const histogram = macdLine.map((macd, i) => macd - signalLine[i]);

  return { macdLine, signalLine, histogram };
}

export function calculateBollingerBands(data: number[], period = 20, multiplier = 2) {
  const sma = calculateSMA(data, period);
  const upper: number[] = [];
  const lower: number[] = [];

  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      upper.push(NaN);
      lower.push(NaN);
      continue;
    }

    let sumSq = 0;
    for (let j = 0; j < period; j++) {
      sumSq += Math.pow(data[i - j] - sma[i], 2);
    }
    const stdDev = Math.sqrt(sumSq / period);
    
    upper.push(sma[i] + stdDev * multiplier);
    lower.push(sma[i] - stdDev * multiplier);
  }

  return { middle: sma, upper, lower };
}
