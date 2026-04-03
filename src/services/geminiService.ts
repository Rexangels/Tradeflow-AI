import { GoogleGenAI, Type, FunctionDeclaration, GenerateContentResponse } from "@google/genai";
import { Candle, AgentConfig, Strategy, Timeframe } from "../types";
import { fetchBinanceData } from "./marketData";
import { runBacktest as executeBacktest } from "./backtest";

const apiKey = process.env.GEMINI_API_KEY;
const ai = new GoogleGenAI({ apiKey: apiKey! });

// Tool Definitions
const fetchMarketDataTool: FunctionDeclaration = {
  name: "fetchMarketData",
  description: "Fetch historical candlestick data for a specific symbol and timeframe.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      symbol: { type: Type.STRING, description: "The trading pair, e.g., 'BTC/USDT'" },
      timeframe: { type: Type.STRING, description: "The timeframe, e.g., '1h', '4h', '1d'" }
    },
    required: ["symbol", "timeframe"]
  }
};

const runBacktestTool: FunctionDeclaration = {
  name: "runBacktest",
  description: "Run a backtest simulation with a specific agent configuration and strategies.",
  parameters: {
    type: Type.OBJECT,
    properties: {
      agentName: { type: Type.STRING },
      riskTolerance: { type: Type.NUMBER },
      rewardStyle: { type: Type.STRING, enum: ["aggressive", "conservative", "balanced"] },
      strategies: { 
        type: Type.ARRAY, 
        items: { type: Type.STRING },
        description: "List of strategies to enable: 'Trend Following', 'Mean Reversion', 'Volatility Breakout'"
      }
    },
    required: ["agentName", "riskTolerance", "rewardStyle", "strategies"]
  }
};

const model = "gemini-3.1-pro-preview";

export const chat = ai.chats.create({
  model: model,
  config: {
    systemInstruction: `You are the TradeFlow AI Orchestrator. 
    Your goal is to help the user manage their trading workflow.
    You can fetch market data, run backtests, and search for news to provide context.
    When the user asks for news or market sentiment, use the googleSearch tool.
    When the user wants to test a strategy, use the runBacktest tool.
    Always explain your reasoning before taking action.
    If the user gives suggestions, incorporate them into the tool parameters.`,
    tools: [
      { googleSearch: {} },
      { functionDeclarations: [fetchMarketDataTool, runBacktestTool] }
    ],
    toolConfig: { includeServerSideToolInvocations: true }
  }
});

export async function sendMessage(message: string) {
  try {
    const response = await chat.sendMessage({ message });
    return response;
  } catch (error) {
    console.error("Gemini Error:", error);
    throw error;
  }
}

// Helper to handle tool calls (to be used in the UI component)
export async function handleToolCall(functionCall: any, currentData: { marketData: Candle[] }) {
  const { name, args } = functionCall;

  if (name === "fetchMarketData") {
    const data = await fetchBinanceData(args.symbol, args.timeframe as Timeframe);
    return { data, message: `Fetched ${data.length} candles for ${args.symbol} (${args.timeframe}).` };
  }

  if (name === "runBacktest") {
    const agent: AgentConfig = {
      id: "ai-gen-" + Date.now(),
      name: args.agentName,
      type: "custom",
      riskTolerance: args.riskTolerance,
      rewardStyle: args.rewardStyle,
      holdingBehavior: "short-term"
    };
    
    const enabledStrategies: Strategy[] = args.strategies.map((s: string) => ({
      id: s.toLowerCase().replace(/\s/g, "-"),
      name: s,
      desc: "AI suggested strategy",
      enabled: true
    }));

    const result = executeBacktest(currentData.marketData, agent, enabledStrategies);
    return { result, agent, strategies: enabledStrategies, message: `Backtest completed. Profit: ${result.totalProfit}%.` };
  }

  return null;
}
