from django.urls import path

from .views import (
    AdminSessionView,
    AgentDetailView,
    AgentsView,
    AiChatView,
    BacktestDetailView,
    BacktestsView,
    HealthView,
    MarketDataCandlesView,
    PaperTradingAccountView,
    PaperTradingOrdersView,
    PaperTradingSessionView,
    SettingsView,
)


urlpatterns = [
    path("health", HealthView.as_view()),
    path("admin/session", AdminSessionView.as_view()),
    path("agents", AgentsView.as_view()),
    path("agents/<uuid:agent_id>", AgentDetailView.as_view()),
    path("market-data/candles", MarketDataCandlesView.as_view()),
    path("backtests", BacktestsView.as_view()),
    path("backtests/<uuid:backtest_id>", BacktestDetailView.as_view()),
    path("paper-trading/account", PaperTradingAccountView.as_view()),
    path("paper-trading/orders", PaperTradingOrdersView.as_view()),
    path("paper-trading/sessions/<uuid:session_id>", PaperTradingSessionView.as_view()),
    path("ai/chat", AiChatView.as_view()),
    path("settings", SettingsView.as_view()),
]
