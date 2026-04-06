from datetime import datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from rest_framework.test import APIClient, APITestCase

from platform_api.auth_utils import ensure_admin_user
from platform_api.models import Agent, BacktestRun, BacktestTrade


@override_settings(
    DJANGO_ADMIN_EMAIL="operator@example.com",
    DJANGO_ADMIN_PASSWORD="super-secret-password",
)
class AiChatApiTests(APITestCase):
    def setUp(self):
        self.user = ensure_admin_user()
        self.client = APIClient()
        self.client.force_login(self.user)

    @patch(
        "platform_api.services.ai_orchestrator.get_candles",
        side_effect=ValueError("Unable to load Binance market data for BTCUSDT on 1h."),
    )
    def test_chat_returns_graceful_reply_when_market_data_is_unavailable(self, _mock_get_candles):
        response = self.client.post(
            "/api/v1/ai/chat",
            {
                "message": "Give me a quick market read for BTCUSDT.",
                "symbol": "BTCUSDT",
                "timeframe": "1h",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("threadId", response.data)
        self.assertGreaterEqual(len(response.data["messages"]), 3)
        self.assertIn("currently unavailable", response.data["messages"][1]["content"])
        self.assertIn("backend tool results", response.data["reply"])

    @patch("platform_api.services.ai_orchestrator.latest_price", return_value=202.5)
    @patch(
        "platform_api.services.ai_orchestrator.get_candles",
        return_value=[
            {"time": "2026-04-05T00:00:00+00:00", "open": 200, "high": 203, "low": 199, "close": 201, "volume": 1000},
            {"time": "2026-04-05T01:00:00+00:00", "open": 201, "high": 204, "low": 200, "close": 202, "volume": 1005},
        ] * 200,
    )
    @patch(
        "platform_api.services.ai_orchestrator.run_backtest",
        return_value={
            "metrics": {
                "totalReturnPct": 4.2,
                "maxDrawdownPct": 2.1,
                "sharpeRatio": 1.9,
                "winRate": 62.5,
                "totalTrades": 8,
            },
            "modelAnalysis": {
                "signal": {
                    "action": "buy",
                    "probabilityUpPct": 67.4,
                    "confidencePct": 17.4,
                },
                "performance": {
                    "testAccuracyPct": 57.1,
                    "testPrecisionPct": 59.4,
                },
                "explanation": {
                    "summary": "The baseline model sees a 67.40% probability of positive forward returns and currently leans BUY."
                },
            },
        },
    )
    def test_chat_includes_model_analysis_context_for_model_questions(self, _mock_backtest, _mock_candles, _mock_price):
        response = self.client.post(
            "/api/v1/ai/chat",
            {
                "message": "Explain the model signal for ETHUSDT.",
                "symbol": "ETHUSDT",
                "timeframe": "1h",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        tool_messages = [message["content"] for message in response.data["messages"] if message["role"] == "tool"]
        self.assertTrue(any("Model analysis for ETHUSDT" in message for message in tool_messages))

    @override_settings(
        DJANGO_ADMIN_EMAIL="operator@example.com",
        DJANGO_ADMIN_PASSWORD="super-secret-password",
        GEMINI_API_KEY="bad-key",
    )
    @patch("platform_api.services.ai_orchestrator.genai")
    @patch("platform_api.services.ai_orchestrator.latest_price", return_value=202.5)
    @patch(
        "platform_api.services.ai_orchestrator.get_candles",
        return_value=[
            {"time": "2026-04-05T00:00:00+00:00", "open": 200, "high": 203, "low": 199, "close": 201, "volume": 1000},
            {"time": "2026-04-05T01:00:00+00:00", "open": 201, "high": 204, "low": 200, "close": 202, "volume": 1005},
        ] * 200,
    )
    def test_chat_falls_back_when_gemini_provider_rejects_the_key(self, _mock_candles, _mock_price, mock_genai):
        mock_models = SimpleNamespace(generate_content=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("API key not valid.")))
        mock_genai.Client.return_value = SimpleNamespace(models=mock_models)

        response = self.client.post(
            "/api/v1/ai/chat",
            {
                "message": "Give me a quick market read for ETHUSDT.",
                "symbol": "ETHUSDT",
                "timeframe": "1h",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("Gemini is unavailable right now", response.data["reply"])
        self.assertIn("backend tool results", response.data["reply"])

    def test_chat_can_explain_a_saved_backtest_without_gemini(self):
        agent = Agent.objects.create(
            owner=self.user,
            name="Trend Research Template",
            type="template",
            reward_style="balanced",
            risk_tolerance=0.4,
            holding_behavior="short-term",
            strategies=[
                {
                    "id": "trend-following",
                    "name": "Trend Following",
                    "description": "EMA crossover entries with momentum-aware exits.",
                    "enabled": True,
                },
                {
                    "id": "mean-reversion",
                    "name": "Mean Reversion",
                    "description": "Bollinger Band fades filtered by RSI exhaustion.",
                    "enabled": True,
                },
            ],
        )
        run = BacktestRun.objects.create(
            owner=self.user,
            agent=agent,
            symbol="ETHUSDT",
            timeframe="1h",
            settings={"startingBalance": 10000},
            metrics={
                "totalReturnPct": 2.4,
                "benchmarkReturnPct": 74.43,
                "excessReturnPct": -72.03,
                "sharpeRatio": 5.67,
                "maxDrawdownPct": 1.31,
                "winRate": 75,
                "totalTrades": 16,
                "exposureTimePct": 6.6,
            },
            validation={
                "candlesChecked": 500,
                "isSorted": True,
                "warnings": [
                    "Walk-forward test windows underperformed buy-and-hold on average.",
                    "No out-of-sample walk-forward window beat buy-and-hold.",
                ],
                "walkForward": {
                    "available": True,
                    "verdict": "fail",
                    "trainCandlesPerWindow": 250,
                    "testCandlesPerWindow": 100,
                    "windowCount": 3,
                    "benchmarkBeatRatePct": 0,
                    "profitableWindowPct": 33.33,
                    "averageTestReturnPct": -0.14,
                    "averageTestBenchmarkReturnPct": 10.79,
                    "averageTestExcessReturnPct": -10.94,
                    "averageTestSharpeRatio": -2.56,
                    "averageTestDrawdownPct": 0.52,
                    "warnings": [],
                    "windows": [],
                },
                "modelAnalysis": {
                    "available": True,
                    "modelType": "baseline_logistic_regression",
                    "labelHorizonBars": 6,
                    "trainSamples": 366,
                    "testSamples": 95,
                    "featuresUsed": ["EMA spread"],
                    "performance": {
                        "trainAccuracyPct": 91.0,
                        "testAccuracyPct": 92.63,
                        "testPrecisionPct": 98.11,
                        "testRecallPct": 89.66,
                        "testAverageForwardReturnPct": 0.68,
                        "predictedLongHitRatePct": 100.0,
                    },
                    "signal": {
                        "asOf": "2026-04-05T00:17:00+00:00",
                        "action": "buy",
                        "confidencePct": 60.95,
                        "probabilityUpPct": 80.47,
                        "probabilityDownPct": 19.53,
                    },
                    "topFeatures": [],
                    "explanation": {
                        "summary": "The tuned baseline model sees a 80.47% probability of positive forward returns and currently leans BUY.",
                        "reasoning": [],
                        "caveats": [],
                        "asOf": "2026-04-05T00:17:00+00:00",
                    },
                    "tuning": {
                        "enabled": True,
                        "adaptationMode": "scheduled_retrain",
                        "objective": "validation_quality_score",
                        "candidateCount": 16,
                        "trainSamples": 254,
                        "validationSamples": 112,
                        "testSamples": 95,
                        "selectedConfig": {
                            "horizonBars": 6,
                            "learningRate": 0.12,
                            "regularization": 0.0005,
                            "buyThreshold": 0.56,
                            "sellThreshold": 0.44,
                            "epochs": 220,
                        },
                        "bestValidationScore": 102.9,
                        "validationPerformance": {
                            "accuracyPct": 92.86,
                            "precisionPct": 98.25,
                            "recallPct": 90.0,
                            "predictedLongHitRatePct": 100.0,
                            "predictedLongCount": 52,
                            "averageForwardReturnPct": 0.72,
                        },
                        "topTrials": [],
                    },
                },
            },
            equity_curve=[],
        )

        response = self.client.post(
            "/api/v1/ai/chat",
            {
                "message": "Explain this run in plain English.",
                "backtestId": str(run.id),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("lagged by 72.03 percentage points", response.data["reply"])
        self.assertIn("short-horizon forecast", response.data["reply"])

    def test_chat_can_focus_on_a_selected_trade_during_replay(self):
        agent = Agent.objects.create(
            owner=self.user,
            name="Trend Research Template",
            type="template",
            reward_style="balanced",
            risk_tolerance=0.4,
            holding_behavior="short-term",
            strategies=[
                {
                    "id": "trend-following",
                    "name": "Trend Following",
                    "description": "EMA crossover entries with momentum-aware exits.",
                    "enabled": True,
                }
            ],
        )
        run = BacktestRun.objects.create(
            owner=self.user,
            agent=agent,
            symbol="ETHUSDT",
            timeframe="1h",
            settings={"startingBalance": 10000},
            metrics={
                "totalReturnPct": 2.4,
                "benchmarkReturnPct": 74.43,
                "excessReturnPct": -72.03,
                "sharpeRatio": 5.67,
                "maxDrawdownPct": 1.31,
                "winRate": 75,
                "totalTrades": 2,
                "exposureTimePct": 6.6,
            },
            validation={
                "candlesChecked": 500,
                "isSorted": True,
                "warnings": [],
            },
            equity_curve=[],
        )
        entry = BacktestTrade.objects.create(
            backtest_run=run,
            type="buy",
            price=273.38,
            executed_at=datetime(2026, 3, 27, 16, 17, tzinfo=dt_timezone.utc),
            quantity=1.0,
            notional=273.38,
            fee_paid=0.27,
            reason="Strategy entry signal confirmed.",
        )
        BacktestTrade.objects.create(
            backtest_run=run,
            type="sell",
            price=274.9,
            executed_at=datetime(2026, 3, 27, 18, 17, tzinfo=dt_timezone.utc),
            quantity=1.0,
            notional=274.9,
            fee_paid=0.27,
            profit=1.52,
            reason="Strategy exit conditions met.",
        )

        response = self.client.post(
            "/api/v1/ai/chat",
            {
                "message": "Explain this trade.",
                "backtestId": str(run.id),
                "tradeId": str(entry.id),
                "replayTime": "2026-03-27T16:17:00+00:00",
                "playbackIndex": 377,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("This BUY happened here because", response.data["reply"])
        self.assertIn("Strategy entry signal confirmed.", response.data["reply"])
        self.assertIn("paired trade", response.data["reply"])
