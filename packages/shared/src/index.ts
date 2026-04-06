import { z } from "zod";

export const timeframeSchema = z.enum(["1m", "5m", "15m", "1h", "4h", "1d"]);
export type Timeframe = z.infer<typeof timeframeSchema>;

export const rewardStyleSchema = z.enum(["aggressive", "balanced", "conservative"]);
export type RewardStyle = z.infer<typeof rewardStyleSchema>;

export const holdingBehaviorSchema = z.enum(["short-term", "swing", "long-term"]);
export type HoldingBehavior = z.infer<typeof holdingBehaviorSchema>;

export const tradeSideSchema = z.enum(["buy", "sell"]);
export type TradeSide = z.infer<typeof tradeSideSchema>;

export const candleSchema = z.object({
  time: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number(),
});
export type Candle = z.infer<typeof candleSchema>;

export const strategySchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  enabled: z.boolean(),
});
export type Strategy = z.infer<typeof strategySchema>;

export const agentConfigSchema = z.object({
  id: z.string(),
  name: z.string().min(2).max(80),
  type: z.enum(["template", "custom"]),
  rewardStyle: rewardStyleSchema,
  riskTolerance: z.number().min(0).max(1),
  holdingBehavior: holdingBehaviorSchema,
  strategies: z.array(strategySchema).default([]),
  createdAt: z.string().optional(),
  updatedAt: z.string().optional(),
});
export type AgentConfig = z.infer<typeof agentConfigSchema>;

export const upsertAgentSchema = agentConfigSchema.omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});
export type UpsertAgentInput = z.infer<typeof upsertAgentSchema>;

export const marketDataQuerySchema = z.object({
  symbol: z.string().min(3).transform((value) => value.toUpperCase()),
  timeframe: timeframeSchema,
  limit: z.coerce.number().int().min(50).max(1000).default(500),
  forceRefresh: z.coerce.boolean().optional().default(false),
});
export type MarketDataQuery = z.infer<typeof marketDataQuerySchema>;

export const backtestSettingsSchema = z.object({
  startingBalance: z.number().positive().default(10000),
  feeRate: z.number().min(0).max(0.02).default(0.001),
  slippageRate: z.number().min(0).max(0.02).default(0.0005),
  positionSizeFraction: z.number().min(0.05).max(1).default(0.95),
});
export type BacktestSettings = z.infer<typeof backtestSettingsSchema>;

export const backtestRequestSchema = z.object({
  symbol: z.string().min(3).transform((value) => value.toUpperCase()),
  timeframe: timeframeSchema,
  candles: z.array(candleSchema).optional(),
  limit: z.number().int().min(50).max(1000).optional(),
  agent: upsertAgentSchema.extend({
    id: z.string().optional(),
    strategies: z.array(strategySchema).min(1),
  }),
  settings: backtestSettingsSchema.default({
    startingBalance: 10000,
    feeRate: 0.001,
    slippageRate: 0.0005,
    positionSizeFraction: 0.95,
  }),
});
export type BacktestRequest = z.infer<typeof backtestRequestSchema>;

export const equityPointSchema = z.object({
  time: z.string(),
  value: z.number(),
});
export type EquityPoint = z.infer<typeof equityPointSchema>;

export const executedTradeSchema = z.object({
  id: z.string(),
  type: tradeSideSchema,
  price: z.number(),
  time: z.string(),
  quantity: z.number(),
  notional: z.number(),
  feePaid: z.number(),
  profit: z.number().optional(),
  reason: z.string(),
});
export type ExecutedTrade = z.infer<typeof executedTradeSchema>;

export const backtestMetricsSchema = z.object({
  totalReturnPct: z.number(),
  totalProfit: z.number(),
  maxDrawdownPct: z.number(),
  sharpeRatio: z.number(),
  winRate: z.number(),
  totalTrades: z.number().int(),
  endingBalance: z.number(),
  benchmarkReturnPct: z.number(),
  benchmarkEndingBalance: z.number(),
  excessReturnPct: z.number(),
  profitFactor: z.number(),
  expectancy: z.number(),
  exposureTimePct: z.number(),
});
export type BacktestMetrics = z.infer<typeof backtestMetricsSchema>;

export const backtestValidationSchema = z.object({
  candlesChecked: z.number().int(),
  isSorted: z.boolean(),
  warnings: z.array(z.string()),
});
export type BacktestValidation = z.infer<typeof backtestValidationSchema>;

export const backtestWalkForwardWindowSchema = z.object({
  index: z.number().int(),
  trainStart: z.string(),
  trainEnd: z.string(),
  testStart: z.string(),
  testEnd: z.string(),
  trainReturnPct: z.number(),
  trainBenchmarkReturnPct: z.number(),
  testReturnPct: z.number(),
  testBenchmarkReturnPct: z.number(),
  testExcessReturnPct: z.number(),
  testSharpeRatio: z.number(),
  testMaxDrawdownPct: z.number(),
  testTotalTrades: z.number().int(),
});
export type BacktestWalkForwardWindow = z.infer<typeof backtestWalkForwardWindowSchema>;

export const backtestWalkForwardSchema = z.object({
  available: z.boolean(),
  verdict: z.string(),
  trainCandlesPerWindow: z.number().int(),
  testCandlesPerWindow: z.number().int(),
  windowCount: z.number().int(),
  benchmarkBeatRatePct: z.number(),
  profitableWindowPct: z.number(),
  averageTestReturnPct: z.number(),
  averageTestBenchmarkReturnPct: z.number(),
  averageTestExcessReturnPct: z.number(),
  averageTestSharpeRatio: z.number(),
  averageTestDrawdownPct: z.number(),
  warnings: z.array(z.string()),
  windows: z.array(backtestWalkForwardWindowSchema),
});
export type BacktestWalkForward = z.infer<typeof backtestWalkForwardSchema>;

export const modelFeatureContributionSchema = z.object({
  name: z.string(),
  label: z.string(),
  value: z.number(),
  contribution: z.number(),
  effect: z.enum(["supports_upside", "leans_downside"]),
  detail: z.string(),
});
export type ModelFeatureContribution = z.infer<typeof modelFeatureContributionSchema>;

export const modelExplanationSchema = z.object({
  summary: z.string(),
  reasoning: z.array(z.string()),
  caveats: z.array(z.string()),
  asOf: z.string(),
});
export type ModelExplanation = z.infer<typeof modelExplanationSchema>;

export const backtestModelAnalysisSchema = z.object({
  available: z.boolean(),
  modelType: z.string(),
  labelHorizonBars: z.number().int(),
  trainSamples: z.number().int(),
  testSamples: z.number().int(),
  featuresUsed: z.array(z.string()),
  performance: z.object({
    trainAccuracyPct: z.number(),
    testAccuracyPct: z.number(),
    testPrecisionPct: z.number(),
    testRecallPct: z.number(),
    testAverageForwardReturnPct: z.number(),
    predictedLongHitRatePct: z.number(),
  }),
  signal: z.object({
    asOf: z.string(),
    action: z.enum(["buy", "hold", "sell"]),
    confidencePct: z.number(),
    probabilityUpPct: z.number(),
    probabilityDownPct: z.number(),
  }),
  topFeatures: z.array(modelFeatureContributionSchema),
  explanation: modelExplanationSchema,
  tuning: z.object({
    enabled: z.boolean(),
    adaptationMode: z.string(),
    objective: z.string(),
    candidateCount: z.number().int(),
    trainSamples: z.number().int(),
    validationSamples: z.number().int(),
    testSamples: z.number().int(),
    selectedConfig: z.object({
      horizonBars: z.number().int(),
      learningRate: z.number(),
      regularization: z.number(),
      buyThreshold: z.number(),
      sellThreshold: z.number(),
      epochs: z.number().int(),
    }),
    bestValidationScore: z.number(),
    validationPerformance: z.object({
      accuracyPct: z.number(),
      precisionPct: z.number(),
      recallPct: z.number(),
      predictedLongHitRatePct: z.number(),
      predictedLongCount: z.number().int(),
      averageForwardReturnPct: z.number(),
    }),
    topTrials: z.array(
      z.object({
        validationScore: z.number(),
        horizonBars: z.number().int(),
        learningRate: z.number(),
        regularization: z.number(),
        buyThreshold: z.number(),
        sellThreshold: z.number(),
        accuracyPct: z.number(),
        precisionPct: z.number(),
        recallPct: z.number(),
        predictedLongHitRatePct: z.number(),
        predictedLongCount: z.number().int(),
        averageForwardReturnPct: z.number(),
      }),
    ),
  }),
});
export type BacktestModelAnalysis = z.infer<typeof backtestModelAnalysisSchema>;

export const backtestResultSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  timeframe: timeframeSchema,
  agent: agentConfigSchema,
  settings: backtestSettingsSchema,
  metrics: backtestMetricsSchema,
  validation: backtestValidationSchema,
  walkForward: backtestWalkForwardSchema.optional(),
  modelAnalysis: backtestModelAnalysisSchema.optional(),
  equityCurve: z.array(equityPointSchema),
  trades: z.array(executedTradeSchema),
  createdAt: z.string(),
});
export type BacktestResult = z.infer<typeof backtestResultSchema>;

export const loginRequestSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});
export type LoginRequest = z.infer<typeof loginRequestSchema>;

export const adminSessionSchema = z.object({
  isAuthenticated: z.boolean(),
  email: z.string().email().nullable(),
});
export type AdminSession = z.infer<typeof adminSessionSchema>;

export const paperOrderRequestSchema = z.object({
  symbol: z.string().min(3).transform((value) => value.toUpperCase()),
  side: tradeSideSchema,
  quantity: z.number().positive().optional(),
  notional: z.number().positive().optional(),
  timeframe: timeframeSchema.default("1h"),
  sessionId: z.string().optional(),
}).refine((value) => value.quantity || value.notional, {
  message: "quantity or notional is required",
  path: ["quantity"],
});
export type PaperOrderRequest = z.infer<typeof paperOrderRequestSchema>;

export const paperPositionSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  quantity: z.number(),
  averageEntryPrice: z.number(),
  marketPrice: z.number(),
  marketValue: z.number(),
  unrealizedPnl: z.number(),
  updatedAt: z.string(),
});
export type PaperPosition = z.infer<typeof paperPositionSchema>;

export const paperOrderSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  side: tradeSideSchema,
  quantity: z.number(),
  fillPrice: z.number(),
  notional: z.number(),
  feePaid: z.number(),
  realizedPnl: z.number(),
  status: z.enum(["filled"]),
  createdAt: z.string(),
});
export type PaperOrder = z.infer<typeof paperOrderSchema>;

export const paperRiskPolicySchema = z.object({
  tradingEnabled: z.boolean(),
  maxOrderNotional: z.number(),
  maxOpenPositions: z.number().int(),
  maxDailyLoss: z.number(),
  currentOpenPositions: z.number().int(),
  dailyRealizedLoss: z.number(),
});
export type PaperRiskPolicy = z.infer<typeof paperRiskPolicySchema>;

export const paperAccountSchema = z.object({
  id: z.string(),
  cashBalance: z.number(),
  equity: z.number(),
  realizedPnl: z.number(),
  updatedAt: z.string(),
  positions: z.array(paperPositionSchema),
  recentOrders: z.array(paperOrderSchema),
  riskPolicy: paperRiskPolicySchema,
});
export type PaperAccount = z.infer<typeof paperAccountSchema>;

export const paperSessionSchema = z.object({
  id: z.string(),
  createdAt: z.string(),
  orders: z.array(paperOrderSchema),
  positions: z.array(paperPositionSchema),
  cashBalance: z.number(),
  equity: z.number(),
});
export type PaperSession = z.infer<typeof paperSessionSchema>;

export const aiChatRequestSchema = z.object({
  threadId: z.string().optional(),
  message: z.string().min(1),
  symbol: z.string().optional(),
  timeframe: timeframeSchema.optional(),
  agentId: z.string().optional(),
  backtestId: z.string().optional(),
  tradeId: z.string().optional(),
  replayTime: z.string().optional(),
  playbackIndex: z.number().int().min(0).optional(),
});
export type AiChatRequest = z.infer<typeof aiChatRequestSchema>;

export const aiMessageSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "assistant", "tool"]),
  content: z.string(),
  createdAt: z.string(),
});
export type AiMessage = z.infer<typeof aiMessageSchema>;

export const aiChatResponseSchema = z.object({
  threadId: z.string(),
  reply: z.string(),
  messages: z.array(aiMessageSchema),
});
export type AiChatResponse = z.infer<typeof aiChatResponseSchema>;

export const settingsResponseSchema = z.object({
  planName: z.string(),
  monthlyUsage: z.object({
    backtests: z.number().int(),
    aiMessages: z.number().int(),
    paperOrders: z.number().int(),
  }),
  liveTradingStatus: z.literal("coming_soon"),
  systemStatus: z.object({
    databaseEngine: z.string(),
    sqliteMode: z.boolean(),
    geminiConfigured: z.boolean(),
    marketDataProviderUrl: z.string(),
    marketDataFallbackMode: z.string(),
    paperTradingEnabled: z.boolean(),
    liveTradingEnabled: z.boolean(),
  }),
  riskPolicy: paperRiskPolicySchema,
});
export type SettingsResponse = z.infer<typeof settingsResponseSchema>;

export const dashboardSnapshotSchema = z.object({
  latestBacktests: z.array(backtestResultSchema).default([]),
  paperAccount: paperAccountSchema.nullable(),
  watchlist: z.array(
    z.object({
      symbol: z.string(),
      lastPrice: z.number(),
      changePct: z.number(),
    }),
  ),
});
export type DashboardSnapshot = z.infer<typeof dashboardSnapshotSchema>;

export const DEFAULT_STRATEGIES: Strategy[] = [
  {
    id: "trend-following",
    name: "Trend Following",
    description: "EMA crossover entries with momentum-aware exits.",
    enabled: true,
  },
  {
    id: "mean-reversion",
    name: "Mean Reversion",
    description: "Bollinger Band fades filtered by RSI exhaustion.",
    enabled: false,
  },
];

export const DEFAULT_AGENT_TEMPLATE: AgentConfig = {
  id: "template-trend-balanced",
  name: "Trend Research Template",
  type: "template",
  rewardStyle: "balanced",
  riskTolerance: 0.4,
  holdingBehavior: "short-term",
  strategies: DEFAULT_STRATEGIES,
};
