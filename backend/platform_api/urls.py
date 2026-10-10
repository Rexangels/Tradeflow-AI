from django.urls import path

from .forex_views import (
    ActiveBrokerView,
    AgentCycleView,
    AISignalsView,
    EconomicCalendarView,
    ForexPairDetailView,
    ForexPairsView,
    ForexQuoteView,
    MultiTimeframeConfluenceView,
    RiskCheckView,
    RiskRulesView,
    TradingAccountView,
    TradingOrderDetailView,
    TradingOrdersView,
    TradingPositionDetailView,
    TradingPositionsView,
    TradingSessionsView,
)
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
    # Core Platform
    path("health", HealthView.as_view()),
    path("admin/session", AdminSessionView.as_view()),
    path("agents", AgentsView.as_view()),
    path("agents/<uuid:agent_id>", AgentDetailView.as_view()),
    path("market-data/candles", MarketDataCandlesView.as_view()),
    path("backtests", BacktestsView.as_view()),
    path("backtests/<uuid:backtest_id>", BacktestDetailView.as_view()),
    path("ai/chat", AiChatView.as_view()),
    path("settings", SettingsView.as_view()),

    # Legacy paper trading (maintained for backward compatibility)
    path("paper-trading/account", PaperTradingAccountView.as_view()),
    path("paper-trading/orders", PaperTradingOrdersView.as_view()),
    path("paper-trading/sessions/<uuid:session_id>", PaperTradingSessionView.as_view()),

    # Forex Market Data & Watchlist
    path("forex/pairs", ForexPairsView.as_view()),
    path("forex/pairs/<path:symbol>", ForexPairDetailView.as_view()),
    path("forex/quote/<path:symbol>", ForexQuoteView.as_view()),

    # Broker Execution Gateway (Alpaca & Exness MT5 Cent)
    path("trading/broker", ActiveBrokerView.as_view()),
    path("trading/account", TradingAccountView.as_view()),
    path("trading/positions", TradingPositionsView.as_view()),
    path("trading/positions/<path:symbol>", TradingPositionDetailView.as_view()),
    path("trading/orders", TradingOrdersView.as_view()),
    path("trading/orders/<str:order_id>", TradingOrderDetailView.as_view()),

    # Risk Management Guardrails
    path("risk/rules", RiskRulesView.as_view()),
    path("risk/check", RiskCheckView.as_view()),

    # Market Intelligence, Economic News Shield & Sessions
    path("market/economic-calendar", EconomicCalendarView.as_view()),
    path("market/sessions", TradingSessionsView.as_view()),
    path("market/mtf-confluence/<path:symbol>", MultiTimeframeConfluenceView.as_view()),

    # Autonomous AI Agent Strategy Engine & Signals
    path("ai/agent-cycle", AgentCycleView.as_view()),
    path("signals", AISignalsView.as_view()),
]
