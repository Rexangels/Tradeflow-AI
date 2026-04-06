import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { CandlestickChart } from "../components/CandlestickChart";
import { MetricCard } from "../components/ui/metric-card";
import { api } from "../lib/api";
import { queryClient } from "../lib/query-client";
import { useWorkspaceStore } from "../stores/workspace-store";
import type { AgentConfig, BacktestMetrics, BacktestModelAnalysis, BacktestWalkForward, ExecutedTrade } from "../shared";

const BACKTEST_CANDLE_LIMIT = 500;
const DEFAULT_BACKTEST_BRIEF = "Give me an operator brief for this run: verdict, why it happened, and the next tests worth running.";

type BacktestAssistantRequest = {
  message: string;
  tradeId?: string;
  replayTime?: string;
  playbackIndex?: number;
};

export function BacktestsPage() {
  const { symbol, timeframe, selectedAgent, latestBacktest, setLatestBacktest, setSelectedAgent } = useWorkspaceStore();
  const [playbackIndex, setPlaybackIndex] = useState(BACKTEST_CANDLE_LIMIT - 1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [backtestMessage, setBacktestMessage] = useState(DEFAULT_BACKTEST_BRIEF);
  const [backtestThreadId, setBacktestThreadId] = useState<string | undefined>(undefined);
  const [selectedReplayTradeId, setSelectedReplayTradeId] = useState<string | null>(null);
  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: api.getAgents });
  const candlesQuery = useQuery({
    queryKey: ["candles", symbol, timeframe, BACKTEST_CANDLE_LIMIT],
    queryFn: () => api.getCandles(symbol, timeframe, BACKTEST_CANDLE_LIMIT),
  });

  useEffect(() => {
    if (!selectedAgent && agentsQuery.data?.length) {
      setSelectedAgent(agentsQuery.data[0] ?? null);
    }
  }, [agentsQuery.data, selectedAgent, setSelectedAgent]);

  useEffect(() => {
    const candleCount = candlesQuery.data?.length ?? 0;
    if (!candleCount) {
      setPlaybackIndex(0);
      setIsPlaying(false);
      return;
    }

    setPlaybackIndex(candleCount - 1);
    setIsPlaying(false);
  }, [candlesQuery.data, latestBacktest?.id]);

  useEffect(() => {
    setBacktestThreadId(undefined);
    setBacktestMessage(DEFAULT_BACKTEST_BRIEF);
    setSelectedReplayTradeId(null);
  }, [latestBacktest?.id]);

  useEffect(() => {
    if (!isPlaying) {
      return;
    }

    const candleCount = candlesQuery.data?.length ?? 0;
    if (candleCount === 0 || playbackIndex >= candleCount - 1) {
      setIsPlaying(false);
      return;
    }

    const timer = window.setTimeout(() => {
      setPlaybackIndex((current) => Math.min(candleCount - 1, current + 1));
    }, 450);

    return () => window.clearTimeout(timer);
  }, [candlesQuery.data, isPlaying, playbackIndex]);

  const runBacktestMutation = useMutation({
    mutationFn: async () => {
      if (!selectedAgent) {
        throw new Error("Select or create an agent first.");
      }
      const { id, createdAt, updatedAt, ...agentPayload } = selectedAgent;
      void createdAt;
      void updatedAt;
      return api.runBacktest({
        symbol,
        timeframe,
        limit: BACKTEST_CANDLE_LIMIT,
        agent: {
          ...agentPayload,
          id,
        },
        settings: {
          startingBalance: 10000,
          feeRate: 0.001,
          slippageRate: 0.0005,
          positionSizeFraction: 0.95,
        },
      });
    },
    onSuccess: (result) => {
      setLatestBacktest(result);
      queryClient.invalidateQueries({ queryKey: ["backtests"] });
    },
  });
  const backtestChatMutation = useMutation({
    mutationFn: (request: BacktestAssistantRequest) => {
      if (!latestBacktest) {
        throw new Error("Run a backtest first so the AI can explain that specific result.");
      }
      return api.chat({
        message: request.message,
        symbol: latestBacktest.symbol,
        timeframe: latestBacktest.timeframe,
        agentId: latestBacktest.agent.id,
        backtestId: latestBacktest.id,
        threadId: backtestThreadId,
        tradeId: request.tradeId,
        replayTime: request.replayTime,
        playbackIndex: request.playbackIndex,
      });
    },
    onSuccess: (payload) => {
      setBacktestThreadId(payload.threadId);
    },
  });

  const chartData = candlesQuery.data ?? [];
  const metrics = latestBacktest?.metrics;
  const walkForward = latestBacktest?.walkForward;
  const modelAnalysis = latestBacktest?.modelAnalysis;
  const playbackTime = chartData[playbackIndex]?.time;
  const playedTrades = useMemo(() => {
    if (!latestBacktest || !playbackTime) {
      return latestBacktest?.trades ?? [];
    }
    return latestBacktest.trades.filter((trade) => trade.time <= playbackTime);
  }, [latestBacktest, playbackTime]);
  const selectedReplayTrade = useMemo(
    () => playedTrades.find((trade) => trade.id === selectedReplayTradeId) ?? null,
    [playedTrades, selectedReplayTradeId],
  );
  const interpretation = metrics ? buildBacktestInterpretation(metrics, walkForward, modelAnalysis) : [];
  const strategyNotes = buildStrategyNotes(selectedAgent);
  const backtestChatError = backtestChatMutation.error ? (backtestChatMutation.error as Error).message : null;

  useEffect(() => {
    if (selectedReplayTradeId && !playedTrades.some((trade) => trade.id === selectedReplayTradeId)) {
      setSelectedReplayTradeId(null);
    }
  }, [playedTrades, selectedReplayTradeId]);

  const submitBacktestQuestion = (request: BacktestAssistantRequest) => {
    setBacktestMessage(request.message);
    backtestChatMutation.mutate(request);
  };

  return (
    <div className="space-y-6">
      <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Strategy Research</p>
            <h3 className="mt-2 text-2xl font-semibold">Backtest {symbol} on {timeframe}</h3>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={selectedAgent?.id ?? ""}
              onChange={(event) => {
                const agent = agentsQuery.data?.find((item) => item.id === event.target.value) ?? null;
                setSelectedAgent(agent);
              }}
              className="rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none"
            >
              <option value="">Select agent</option>
              {(agentsQuery.data ?? []).map((agent) => (
                <option key={agent.id} value={agent.id}>
                  {agent.name}
                </option>
              ))}
            </select>
            <button type="button" onClick={() => runBacktestMutation.mutate()} className="rounded-2xl bg-emerald-300 px-4 py-3 font-semibold text-slate-950">
              {runBacktestMutation.isPending ? "Running..." : "Run backtest"}
            </button>
          </div>
        </div>
      </section>

      {metrics ? (
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
          <MetricCard label="Return" value={`${metrics.totalReturnPct.toFixed(2)}%`} tone={metrics.totalReturnPct >= 0 ? "positive" : "warning"} />
          <MetricCard label="Benchmark" value={`${metrics.benchmarkReturnPct.toFixed(2)}%`} tone={metrics.benchmarkReturnPct >= 0 ? "positive" : "warning"} />
          <MetricCard label="Excess Return" value={`${metrics.excessReturnPct.toFixed(2)}%`} tone={metrics.excessReturnPct >= 0 ? "positive" : "warning"} />
          <MetricCard label="Sharpe" value={metrics.sharpeRatio.toFixed(2)} />
          <MetricCard label="Drawdown" value={`${metrics.maxDrawdownPct.toFixed(2)}%`} tone="warning" />
          <MetricCard label="Win Rate" value={`${metrics.winRate.toFixed(2)}%`} />
        </div>
      ) : null}

      {walkForward?.available ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <MetricCard label="Walk-Forward Avg Test" value={`${walkForward.averageTestReturnPct.toFixed(2)}%`} tone={walkForward.averageTestReturnPct >= 0 ? "positive" : "warning"} />
          <MetricCard label="Walk-Forward Avg Excess" value={`${walkForward.averageTestExcessReturnPct.toFixed(2)}%`} tone={walkForward.averageTestExcessReturnPct >= 0 ? "positive" : "warning"} />
          <MetricCard label="Beat Rate" value={`${walkForward.benchmarkBeatRatePct.toFixed(2)}%`} tone={walkForward.benchmarkBeatRatePct >= 50 ? "positive" : "warning"} />
          <MetricCard label="Profitable Windows" value={`${walkForward.profitableWindowPct.toFixed(2)}%`} tone={walkForward.profitableWindowPct >= 50 ? "positive" : "warning"} />
          <MetricCard label="Verdict" value={formatWalkForwardVerdict(walkForward.verdict)} tone={walkForward.verdict === "pass" ? "positive" : walkForward.verdict === "mixed" ? "neutral" : "warning"} />
        </div>
      ) : null}

      {modelAnalysis?.available ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <MetricCard label="Model Signal" value={modelAnalysis.signal.action.toUpperCase()} tone={modelSignalTone(modelAnalysis.signal.action)} />
          <MetricCard label="Upside Probability" value={`${modelAnalysis.signal.probabilityUpPct.toFixed(2)}%`} tone={modelAnalysis.signal.probabilityUpPct >= 50 ? "positive" : "warning"} />
          <MetricCard label="Model Confidence" value={`${modelAnalysis.signal.confidencePct.toFixed(2)}%`} tone={modelAnalysis.signal.confidencePct >= 15 ? "positive" : "warning"} />
          <MetricCard label="Held-Out Accuracy" value={`${modelAnalysis.performance.testAccuracyPct.toFixed(2)}%`} tone={modelAnalysis.performance.testAccuracyPct >= 55 ? "positive" : "warning"} />
          <MetricCard label="Long Hit Rate" value={`${modelAnalysis.performance.predictedLongHitRatePct.toFixed(2)}%`} tone={modelAnalysis.performance.predictedLongHitRatePct >= 50 ? "positive" : "warning"} />
        </div>
      ) : null}

      {latestBacktest || runBacktestMutation.error ? (
        <section className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Proof Checks</p>
            <div className="mt-4 space-y-3 text-sm text-slate-300">
              {latestBacktest ? (
                <>
                  <p>Candles validated: {latestBacktest.validation.candlesChecked}</p>
                  <p>Sorted input: {latestBacktest.validation.isSorted ? "Yes" : "No"}</p>
                  <p>Profit factor: {latestBacktest.metrics.profitFactor.toFixed(2)}</p>
                  <p>Expectancy: ${latestBacktest.metrics.expectancy.toFixed(2)} per closed trade</p>
                  <p>Exposure time: {latestBacktest.metrics.exposureTimePct.toFixed(2)}%</p>
                  <p>Benchmark ending balance: ${latestBacktest.metrics.benchmarkEndingBalance.toFixed(2)}</p>
                  {latestBacktest.validation.warnings.length > 0 ? (
                    <div className="rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-amber-100">
                      {latestBacktest.validation.warnings.map((warning) => (
                        <p key={warning}>{warning}</p>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : (
                <p>Backtest validation details will appear here after a run completes.</p>
              )}
            </div>
          </div>

          <div className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-500">What This Run Means</p>
            {runBacktestMutation.error ? (
              <div className="mt-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-200">
                {(runBacktestMutation.error as Error).message}
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                {interpretation.map((line) => (
                  <div key={line} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-200">
                    {line}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Active Signal Stack</p>
          <div className="mt-4 grid gap-3">
            {strategyNotes.map((note) => (
              <div key={note.title} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-sm font-semibold text-slate-100">{note.title}</p>
                <p className="mt-2 text-sm text-slate-300">{note.body}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-slate-400">
            Reward style, risk tolerance, and holding behavior are descriptive operator settings right now. The executable edge comes from the enabled strategy rules above, not from a trained model yet.
          </p>
        </section>

        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Walk-Forward Validation</p>
              <p className="mt-2 text-sm text-slate-300">
                We slide a training window forward, then judge the next unseen test window. This is the first check that tells us whether the strategy still behaves outside the original sample.
              </p>
            </div>
            {walkForward ? (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-sm text-slate-100">
                {formatWalkForwardVerdict(walkForward.verdict)}
              </div>
            ) : null}
          </div>

          {walkForward?.available ? (
            <>
              <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Windows</p>
                  <p className="mt-2 text-xl font-semibold text-slate-100">{walkForward.windowCount}</p>
                  <p className="mt-2 text-sm text-slate-400">
                    {walkForward.trainCandlesPerWindow} train candles, then {walkForward.testCandlesPerWindow} unseen test candles.
                  </p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Average Test Window</p>
                  <p className={`mt-2 text-xl font-semibold ${walkForward.averageTestReturnPct >= 0 ? "text-emerald-300" : "text-amber-300"}`}>
                    {walkForward.averageTestReturnPct.toFixed(2)}%
                  </p>
                  <p className="mt-2 text-sm text-slate-400">Benchmark: {walkForward.averageTestBenchmarkReturnPct.toFixed(2)}%</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Average Excess</p>
                  <p className={`mt-2 text-xl font-semibold ${walkForward.averageTestExcessReturnPct >= 0 ? "text-emerald-300" : "text-amber-300"}`}>
                    {walkForward.averageTestExcessReturnPct.toFixed(2)}%
                  </p>
                  <p className="mt-2 text-sm text-slate-400">Beat rate: {walkForward.benchmarkBeatRatePct.toFixed(2)}%</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Average Ride Quality</p>
                  <p className="mt-2 text-xl font-semibold text-slate-100">Sharpe {walkForward.averageTestSharpeRatio.toFixed(2)}</p>
                  <p className="mt-2 text-sm text-slate-400">Drawdown {walkForward.averageTestDrawdownPct.toFixed(2)}%</p>
                </div>
              </div>

              {walkForward.warnings.length > 0 ? (
                <div className="mt-5 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
                  {walkForward.warnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              ) : null}

              <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {walkForward.windows.map((window) => (
                  <div key={window.index} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                    <p className="text-sm font-semibold text-slate-100">Window {window.index}</p>
                    <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-500">
                      Train {new Date(window.trainStart).toLocaleDateString()} to {new Date(window.trainEnd).toLocaleDateString()}
                    </p>
                    <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-500">
                      Test {new Date(window.testStart).toLocaleDateString()} to {new Date(window.testEnd).toLocaleDateString()}
                    </p>
                    <div className="mt-3 space-y-2 text-sm text-slate-300">
                      <p>Train return: {window.trainReturnPct.toFixed(2)}%</p>
                      <p>Test return: {window.testReturnPct.toFixed(2)}%</p>
                      <p>Test benchmark: {window.testBenchmarkReturnPct.toFixed(2)}%</p>
                      <p>Test excess: {window.testExcessReturnPct.toFixed(2)}%</p>
                      <p>Test trades: {window.testTotalTrades}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
              {walkForward?.warnings[0] ?? "Run a larger backtest window to unlock walk-forward validation."}
            </div>
          )}
        </section>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Model Intelligence</p>
          {modelAnalysis?.available ? (
            <>
              <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                <p className="text-sm font-semibold text-slate-100">{modelAnalysis.explanation.summary}</p>
                <p className="mt-2 text-sm text-slate-400">
                  Latest model view as of {new Date(modelAnalysis.signal.asOf).toLocaleString()} using a {modelAnalysis.modelType.replaceAll("_", " ")} over a {modelAnalysis.labelHorizonBars}-bar horizon.
                </p>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Train/Test Samples</p>
                  <p className="mt-2 text-xl font-semibold text-slate-100">
                    {modelAnalysis.tuning.trainSamples + modelAnalysis.tuning.validationSamples} / {modelAnalysis.tuning.testSamples}
                  </p>
                  <p className="mt-2 text-sm text-slate-400">
                    {modelAnalysis.tuning.trainSamples} train, {modelAnalysis.tuning.validationSamples} validation, {modelAnalysis.tuning.testSamples} locked test.
                  </p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Held-Out Precision</p>
                  <p className={`mt-2 text-xl font-semibold ${modelAnalysis.performance.testPrecisionPct >= 50 ? "text-emerald-300" : "text-amber-300"}`}>
                    {modelAnalysis.performance.testPrecisionPct.toFixed(2)}%
                  </p>
                  <p className="mt-2 text-sm text-slate-400">Recall {modelAnalysis.performance.testRecallPct.toFixed(2)}%</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Avg Forward Return</p>
                  <p className={`mt-2 text-xl font-semibold ${modelAnalysis.performance.testAverageForwardReturnPct >= 0 ? "text-emerald-300" : "text-amber-300"}`}>
                    {modelAnalysis.performance.testAverageForwardReturnPct.toFixed(2)}%
                  </p>
                  <p className="mt-2 text-sm text-slate-400">On held-out labeled samples.</p>
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Features Used</p>
                  <p className="mt-2 text-xl font-semibold text-slate-100">{modelAnalysis.featuresUsed.length}</p>
                  <p className="mt-2 text-sm text-slate-400">{modelAnalysis.featuresUsed.slice(0, 2).join(" • ")}</p>
                </div>
              </div>

              <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Tuned Configuration</p>
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3 text-sm text-slate-300">
                  <p>Horizon: {modelAnalysis.tuning.selectedConfig.horizonBars} bars</p>
                  <p>Learning rate: {modelAnalysis.tuning.selectedConfig.learningRate.toFixed(2)}</p>
                  <p>Regularization: {modelAnalysis.tuning.selectedConfig.regularization.toFixed(4)}</p>
                  <p>Buy threshold: {modelAnalysis.tuning.selectedConfig.buyThreshold.toFixed(2)}</p>
                  <p>Sell threshold: {modelAnalysis.tuning.selectedConfig.sellThreshold.toFixed(2)}</p>
                  <p>Validation score: {modelAnalysis.tuning.bestValidationScore.toFixed(2)}</p>
                </div>
                <p className="mt-3 text-sm text-slate-400">
                  The tuner searched {modelAnalysis.tuning.candidateCount} candidate configurations using a time-ordered validation slice, then kept the test slice locked for the final check.
                </p>
              </div>

              <div className="mt-5 grid gap-3 md:grid-cols-2">
                {modelAnalysis.explanation.reasoning.map((reason) => (
                  <div key={reason} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-200">
                    {reason}
                  </div>
                ))}
              </div>

              <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Top Tuning Trials</p>
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  {modelAnalysis.tuning.topTrials.map((trial, index) => (
                    <div key={`${trial.horizonBars}-${trial.learningRate}-${trial.regularization}-${index}`} className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-slate-100">Trial {index + 1}</p>
                        <p className="text-sm text-cyan-200">Score {trial.validationScore.toFixed(2)}</p>
                      </div>
                      <div className="mt-3 space-y-2 text-sm text-slate-300">
                        <p>Horizon {trial.horizonBars} bars • LR {trial.learningRate.toFixed(2)} • Reg {trial.regularization.toFixed(4)}</p>
                        <p>Thresholds {trial.buyThreshold.toFixed(2)} / {trial.sellThreshold.toFixed(2)}</p>
                        <p>Accuracy {trial.accuracyPct.toFixed(2)}% • Precision {trial.precisionPct.toFixed(2)}%</p>
                        <p>Long hit rate {trial.predictedLongHitRatePct.toFixed(2)}% • Long calls {trial.predictedLongCount}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {modelAnalysis.explanation.caveats.length > 0 ? (
                <div className="mt-5 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
                  {modelAnalysis.explanation.caveats.map((caveat) => (
                    <p key={caveat}>{caveat}</p>
                  ))}
                </div>
              ) : null}
            </>
          ) : (
            <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
              {modelAnalysis?.explanation.summary ?? "Run a fresh backtest to generate the baseline model analysis."}
            </div>
          )}
        </section>

        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Why The Model Thinks That</p>
          {modelAnalysis?.available ? (
            <div className="mt-4 space-y-3">
              {modelAnalysis.topFeatures.map((feature) => (
                <div key={feature.name} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-slate-100">{feature.label}</p>
                    <p className={feature.effect === "supports_upside" ? "text-sm font-semibold text-emerald-300" : "text-sm font-semibold text-amber-300"}>
                      {feature.effect === "supports_upside" ? "Supports upside" : "Leans downside"}
                    </p>
                  </div>
                  <p className="mt-2 text-sm text-slate-300">{feature.detail}</p>
                  <div className="mt-3 flex flex-wrap gap-3 text-xs uppercase tracking-[0.14em] text-slate-500">
                    <span>Feature value {feature.value.toFixed(4)}</span>
                    <span>Contribution {feature.contribution.toFixed(4)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
              The explanation layer appears after a fresh model-backed backtest run.
            </div>
          )}
        </section>
      </section>

      <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Research Assistant</p>
          <h3 className="mt-2 text-2xl font-semibold">Ask about this exact run</h3>
          <p className="mt-3 text-sm text-slate-400">
            This assistant uses the saved backtest you just ran, including the rule stack, walk-forward verdict, tuned model output, and replay focus you select from the chart or execution log.
          </p>
          <textarea
            value={backtestMessage}
            onChange={(event) => setBacktestMessage(event.target.value)}
            className="mt-5 min-h-32 w-full rounded-3xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none"
          />
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => submitBacktestQuestion({ message: backtestMessage })}
              className="rounded-2xl bg-cyan-300 px-4 py-3 font-semibold text-slate-950"
            >
              {backtestChatMutation.isPending ? "Thinking..." : "Generate Brief"}
            </button>
            <button
              type="button"
              onClick={() => setBacktestMessage("Why is the model BUY while the strategy fails out of sample?")}
              className="rounded-2xl border border-slate-700 bg-slate-900/80 px-4 py-3 text-sm text-slate-200"
            >
              Explain Model vs Strategy
            </button>
            <button
              type="button"
              onClick={() => setBacktestMessage("What should I change next in the rule logic, model tuning, or risk settings?")}
              className="rounded-2xl border border-slate-700 bg-slate-900/80 px-4 py-3 text-sm text-slate-200"
            >
              Suggest Next Experiments
            </button>
          </div>
          {backtestChatError ? (
            <div className="mt-4 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100">
              {backtestChatError}
            </div>
          ) : null}
        </section>

        <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
          <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Run Conversation</p>
          <div className="mt-4 space-y-3">
            {(backtestChatMutation.data?.messages ?? []).length > 0 ? (
              backtestChatMutation.data?.messages.map((entry) => (
                <div key={entry.id} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm">
                  <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{entry.role}</p>
                  <p className="mt-2 whitespace-pre-wrap text-slate-200">{entry.content}</p>
                </div>
              ))
            ) : (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
                Run a backtest, then generate an operator brief, ask why the model and strategy disagree, or request the next experiments worth testing.
              </div>
            )}
          </div>
        </section>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-6">
          {chartData.length > 0 && latestBacktest ? (
            <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Strategy replay</p>
                  <p className="mt-2 text-sm text-slate-300">
                    Scrub from past to future to see entries and exits appear as the agent would have seen them. Past candles stay bright; future candles stay faded.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setIsPlaying((current) => !current)}
                    className="rounded-2xl border border-cyan-500/30 bg-cyan-500/10 px-4 py-3 text-sm font-semibold text-cyan-100"
                  >
                    {isPlaying ? "Pause Replay" : "Play Replay"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsPlaying(false);
                      setPlaybackIndex(0);
                    }}
                    className="rounded-2xl border border-slate-700 bg-slate-900/80 px-4 py-3 text-sm text-slate-200"
                  >
                    Restart
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsPlaying(false);
                      setPlaybackIndex(Math.max(0, playbackIndex - 1));
                    }}
                    className="rounded-2xl border border-slate-700 bg-slate-900/80 px-4 py-3 text-sm text-slate-200"
                  >
                    Step Back
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setIsPlaying(false);
                      setPlaybackIndex(Math.min(chartData.length - 1, playbackIndex + 1));
                    }}
                    className="rounded-2xl border border-slate-700 bg-slate-900/80 px-4 py-3 text-sm text-slate-200"
                  >
                    Step Forward
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      submitBacktestQuestion({
                        message: buildReplayMomentPrompt(playbackTime, playbackIndex, playedTrades.length),
                        replayTime: playbackTime,
                        playbackIndex,
                      })
                    }
                    disabled={!playbackTime}
                    className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm font-semibold text-amber-100 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Explain Current Replay Moment
                  </button>
                </div>
              </div>

              <div className="mt-5">
                <input
                  aria-label="Replay progress"
                  type="range"
                  min={0}
                  max={Math.max(0, chartData.length - 1)}
                  value={Math.min(playbackIndex, Math.max(0, chartData.length - 1))}
                  onChange={(event) => {
                    setIsPlaying(false);
                    setPlaybackIndex(Number(event.target.value));
                  }}
                  className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-800 accent-emerald-300"
                />
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400">
                  <span>
                    Replay bar {Math.min(playbackIndex + 1, chartData.length)} of {chartData.length}
                  </span>
                  <span>{playbackTime ? new Date(playbackTime).toLocaleString() : "No candle loaded"}</span>
                  <span>{playedTrades.length} trade events revealed</span>
                </div>
              </div>
            </section>
          ) : null}

          <CandlestickChart
            data={chartData}
            trades={latestBacktest?.trades ?? []}
            playbackIndex={latestBacktest ? playbackIndex : undefined}
            selectedTradeId={selectedReplayTrade?.id ?? undefined}
            onTradeSelect={(trade) => {
              setSelectedReplayTradeId(trade.id);
              setBacktestMessage(buildTradePrompt(trade));
            }}
          />
        </div>

        <div className="space-y-6">
          {latestBacktest ? (
            <>
              <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Replay Snapshot</p>
                <div className="mt-4 space-y-3 text-sm text-slate-300">
                  <p>Current candle: {playbackTime ? new Date(playbackTime).toLocaleString() : "Not loaded yet"}</p>
                  <p>Visible trade events: {playedTrades.length}</p>
                  <p>Closed trades in final run: {metrics?.totalTrades ?? 0}</p>
                  <p>Ending balance if you finish the run: ${metrics?.endingBalance.toFixed(2) ?? "0.00"}</p>
                </div>
                {selectedReplayTrade ? (
                  <div className="mt-5 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-amber-200">Selected Trade</p>
                    <div className="mt-3 space-y-2 text-sm text-amber-50">
                      <p>
                        {selectedReplayTrade.type.toUpperCase()} at ${selectedReplayTrade.price.toFixed(2)}
                      </p>
                      <p>{new Date(selectedReplayTrade.time).toLocaleString()}</p>
                      <p>{selectedReplayTrade.reason}</p>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={() =>
                          submitBacktestQuestion({
                            message: buildTradePrompt(selectedReplayTrade),
                            tradeId: selectedReplayTrade.id,
                            replayTime: playbackTime,
                            playbackIndex,
                          })
                        }
                        className="rounded-2xl bg-amber-300 px-4 py-3 text-sm font-semibold text-slate-950"
                      >
                        Explain Selected Trade
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedReplayTradeId(null);
                          setBacktestMessage(DEFAULT_BACKTEST_BRIEF);
                        }}
                        className="rounded-2xl border border-slate-700 bg-slate-900/80 px-4 py-3 text-sm text-slate-200"
                      >
                        Clear Selection
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-300">
                    Click a marker on the chart or choose a trade below to ask the assistant why that decision happened.
                  </div>
                )}
              </section>

              <section className="rounded-[2rem] border border-slate-800 bg-slate-950/80 p-6">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Execution log</p>
                <div className="mt-4 space-y-3">
                  {playedTrades.slice(-8).map((trade) => (
                    <div
                      key={trade.id}
                      className={`rounded-2xl border p-4 ${
                        selectedReplayTrade?.id === trade.id
                          ? "border-amber-400/50 bg-amber-500/10"
                          : "border-slate-800 bg-slate-900/60"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={trade.type === "buy" ? "text-emerald-300" : "text-sky-300"}>{trade.type.toUpperCase()}</span>
                        <span>${trade.price.toFixed(2)}</span>
                      </div>
                      <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-500">{new Date(trade.time).toLocaleString()}</p>
                      <p className="mt-2 text-sm text-slate-400">{trade.reason}</p>
                      <div className="mt-4 flex flex-wrap gap-3">
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedReplayTradeId(trade.id);
                            setBacktestMessage(buildTradePrompt(trade));
                          }}
                          className="rounded-2xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs text-slate-200"
                        >
                          Select Trade
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedReplayTradeId(trade.id);
                            submitBacktestQuestion({
                              message: buildTradePrompt(trade),
                              tradeId: trade.id,
                              replayTime: playbackTime,
                              playbackIndex,
                            });
                          }}
                          className="rounded-2xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-xs font-semibold text-cyan-100"
                        >
                          Explain This Trade
                        </button>
                      </div>
                    </div>
                  ))}
                  {playedTrades.length === 0 ? (
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
                      No trades have been revealed at the current replay position yet.
                    </div>
                  ) : null}
                </div>
              </section>
            </>
          ) : null}
        </div>
      </section>
    </div>
  );
}


function buildBacktestInterpretation(metrics: BacktestMetrics, walkForward?: BacktestWalkForward, modelAnalysis?: BacktestModelAnalysis) {
  const lines = [];

  if (metrics.excessReturnPct >= 0) {
    lines.push(`The strategy beat buy-and-hold by ${metrics.excessReturnPct.toFixed(2)} percentage points in this window, which is the first thing to care about.`);
  } else {
    lines.push(`The strategy lagged buy-and-hold by ${Math.abs(metrics.excessReturnPct).toFixed(2)} percentage points, so this run is not attractive yet even though some internal stats look clean.`);
  }

  if (walkForward?.available) {
    if (walkForward.verdict === "pass") {
      lines.push(`The out-of-sample walk-forward check is encouraging: average test-window excess return was ${walkForward.averageTestExcessReturnPct.toFixed(2)}% and the strategy beat the benchmark in ${walkForward.benchmarkBeatRatePct.toFixed(2)}% of windows.`);
    } else if (walkForward.verdict === "mixed") {
      lines.push(`The walk-forward result is mixed: the strategy still needs improvement because average out-of-sample excess return was ${walkForward.averageTestExcessReturnPct.toFixed(2)}% across ${walkForward.windowCount} windows.`);
    } else {
      lines.push(`The walk-forward result is weak: once the window rolled forward, average out-of-sample excess return fell to ${walkForward.averageTestExcessReturnPct.toFixed(2)}%, so the edge is not robust yet.`);
    }
  } else {
    lines.push("Walk-forward validation is not available yet for this run, so we only have an in-sample view of the strategy.");
  }

  if (modelAnalysis?.available) {
    lines.push(`The baseline model currently leans ${modelAnalysis.signal.action.toUpperCase()} with ${modelAnalysis.signal.probabilityUpPct.toFixed(2)}% upside probability and ${modelAnalysis.performance.testAccuracyPct.toFixed(2)}% held-out accuracy, so use it as a second opinion rather than blind authority.`);
  } else {
    lines.push("The model-analysis layer is not available for this run, so there is no learned-signal cross-check yet.");
  }

  lines.push(`Sharpe ${metrics.sharpeRatio.toFixed(2)} and drawdown ${metrics.maxDrawdownPct.toFixed(2)}% describe the ride quality: higher Sharpe and lower drawdown mean smoother returns.`);

  if (metrics.totalTrades < 8) {
    lines.push(`Only ${metrics.totalTrades} closed trades were taken, so win rate ${metrics.winRate.toFixed(2)}% and expectancy $${metrics.expectancy.toFixed(2)} are still a small sample.`);
  } else {
    lines.push(`Win rate ${metrics.winRate.toFixed(2)}%, profit factor ${metrics.profitFactor.toFixed(2)}, and expectancy $${metrics.expectancy.toFixed(2)} show whether each completed trade is pulling its weight.`);
  }

  lines.push(`Exposure time ${metrics.exposureTimePct.toFixed(2)}% means the agent spent most of the period waiting rather than holding risk, which can be good or bad depending on how much return it missed.`);

  return lines;
}

function buildStrategyNotes(agent: AgentConfig | null) {
  const enabledStrategies = agent?.strategies.filter((strategy) => strategy.enabled) ?? [];
  if (enabledStrategies.length === 0) {
    return [
      {
        title: "No active strategy rules",
        body: "Enable at least one strategy template before you expect the backtest engine to produce entries and exits.",
      },
    ];
  }

  return enabledStrategies.map((strategy) => {
    if (strategy.id === "trend-following") {
      return {
        title: "Trend Following",
        body: "Buys when the 9-period EMA crosses above the 21-period EMA, and exits when the fast EMA crosses back below the slow EMA.",
      };
    }
    if (strategy.id === "mean-reversion") {
      return {
        title: "Mean Reversion",
        body: "Buys when price closes below the lower Bollinger Band while RSI is under 35, then exits when price stretches above the upper band or RSI rises above 65.",
      };
    }

    return {
      title: strategy.name,
      body: strategy.description,
    };
  });
}

function buildReplayMomentPrompt(playbackTime?: string, playbackIndex?: number, revealedTrades = 0) {
  if (!playbackTime) {
    return "Explain this replay moment. What had the strategy seen so far, and what should I notice here?";
  }

  return `Explain this replay moment at ${new Date(playbackTime).toLocaleString()} on replay bar ${playbackIndex ?? 0}. What had the strategy seen so far, what was the latest revealed trade, and what should I notice here? ${revealedTrades} trade events were already visible.`;
}

function buildTradePrompt(trade: ExecutedTrade) {
  return `Explain this ${trade.type.toUpperCase()} trade at ${new Date(trade.time).toLocaleString()} around $${trade.price.toFixed(2)}. Why did the strategy act here, what did it likely know at that point, and what should I notice about the outcome?`;
}

function formatWalkForwardVerdict(verdict: string) {
  if (verdict === "pass") {
    return "Out-of-sample pass";
  }
  if (verdict === "mixed") {
    return "Mixed evidence";
  }
  if (verdict === "fail") {
    return "Fails out-of-sample";
  }
  if (verdict === "insufficient_data") {
    return "More data needed";
  }
  return "Unavailable";
}

function modelSignalTone(action: BacktestModelAnalysis["signal"]["action"]) {
  if (action === "buy") {
    return "positive" as const;
  }
  if (action === "sell") {
    return "warning" as const;
  }
  return "neutral" as const;
}
