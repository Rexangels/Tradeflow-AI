from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_utils import ensure_admin_user
from .defaults import DEFAULT_AGENT
from .models import Agent, BacktestRun, BacktestTrade, UsageEvent
from .permissions import IsTradeflowAdmin
from .presenters import serialize_agent, serialize_backtest
from .serializers import (
    AgentPayloadSerializer,
    AiChatSerializer,
    BacktestRequestSerializer,
    LoginSerializer,
    MarketDataQuerySerializer,
    PaperOrderSerializer,
)
from .services.ai_orchestrator import handle_chat
from .services.backtests import run_backtest, trade_timestamp
from .services.market_data import get_candles, latest_price
from .services.paper_trading import account_snapshot, get_risk_policy, place_order, session_snapshot, system_status


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "tradeflow-django-api"})


class AdminSessionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        ensure_admin_user()
        if request.user.is_authenticated:
            return Response({"isAuthenticated": True, "email": request.user.email})
        return Response({"isAuthenticated": False, "email": None})

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ensure_admin_user()
        credentials = serializer.validated_data
        user = authenticate(request, username=credentials["email"], password=credentials["password"])
        if not user:
            return Response({"detail": "Invalid credentials."}, status=401)
        login(request, user)
        return Response({"isAuthenticated": True, "email": user.email})

    def delete(self, request):
        logout(request)
        return Response({"isAuthenticated": False, "email": None})


class AgentsView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        agents = Agent.objects.filter(owner=request.user).order_by("-updated_at")
        return Response([serialize_agent(agent) for agent in agents])

    def post(self, request):
        serializer = AgentPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        agent = Agent.objects.create(
            owner=request.user,
            name=payload["name"],
            type=payload["type"],
            reward_style=payload["rewardStyle"],
            risk_tolerance=payload["riskTolerance"],
            holding_behavior=payload["holdingBehavior"],
            strategies=payload["strategies"],
        )
        return Response(serialize_agent(agent), status=201)


class AgentDetailView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def put(self, request, agent_id):
        serializer = AgentPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        agent = Agent.objects.get(id=agent_id, owner=request.user)
        agent.name = payload["name"]
        agent.type = payload["type"]
        agent.reward_style = payload["rewardStyle"]
        agent.risk_tolerance = payload["riskTolerance"]
        agent.holding_behavior = payload["holdingBehavior"]
        agent.strategies = payload["strategies"]
        agent.save()
        return Response(serialize_agent(agent))


class MarketDataCandlesView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        serializer = MarketDataQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            candles = get_candles(
                payload["symbol"],
                payload["timeframe"],
                limit=payload["limit"],
                force_refresh=payload["forceRefresh"],
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(candles)


class BacktestsView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        runs = BacktestRun.objects.filter(owner=request.user).select_related("agent").prefetch_related("trades").order_by("-created_at")[:20]
        return Response([serialize_backtest(run) for run in runs])

    @transaction.atomic
    def post(self, request):
        serializer = BacktestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        candles = payload.get("candles") or get_candles(payload["symbol"], payload["timeframe"], limit=payload.get("limit", 500))
        try:
            result = run_backtest(payload, candles)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        agent_payload = payload["agent"]
        agent_id = agent_payload.get("id")
        agent = Agent.objects.filter(id=agent_id, owner=request.user).first() if agent_id else None
        if not agent:
            agent = Agent.objects.create(
                owner=request.user,
                name=agent_payload["name"],
                type=agent_payload["type"],
                reward_style=agent_payload["rewardStyle"],
                risk_tolerance=agent_payload["riskTolerance"],
                holding_behavior=agent_payload["holdingBehavior"],
                strategies=agent_payload["strategies"],
            )

        run = BacktestRun.objects.create(
            id=result["id"],
            owner=request.user,
            agent=agent,
            symbol=result["symbol"],
            timeframe=result["timeframe"],
            settings=result["settings"],
            metrics=result["metrics"],
            validation={
                **result["validation"],
                "walkForward": result["walkForward"],
                "modelAnalysis": result["modelAnalysis"],
            },
            equity_curve=result["equityCurve"],
        )

        for trade in result["trades"]:
            BacktestTrade.objects.create(
                id=trade["id"],
                backtest_run=run,
                type=trade["type"],
                price=trade["price"],
                executed_at=trade_timestamp(trade["time"]),
                quantity=trade["quantity"],
                notional=trade["notional"],
                fee_paid=trade["feePaid"],
                profit=trade.get("profit"),
                reason=trade["reason"],
            )

        UsageEvent.objects.create(
            owner=request.user,
            category="backtest",
            reference_id=str(run.id),
            quantity=1,
            metadata={"symbol": run.symbol, "timeframe": run.timeframe},
        )
        run = BacktestRun.objects.select_related("agent").prefetch_related("trades").get(id=run.id)
        return Response(serialize_backtest(run), status=201)


class BacktestDetailView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request, backtest_id):
        run = BacktestRun.objects.select_related("agent").prefetch_related("trades").get(id=backtest_id, owner=request.user)
        return Response(serialize_backtest(run))


class PaperTradingAccountView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        return Response(account_snapshot(request.user))


class PaperTradingOrdersView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def post(self, request):
        serializer = PaperOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = place_order(request.user, serializer.validated_data)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(payload, status=201)


class PaperTradingSessionView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request, session_id):
        return Response(session_snapshot(request.user, session_id))


class AiChatView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def post(self, request):
        serializer = AiChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(handle_chat(request.user, serializer.validated_data))


class SettingsView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        usage = (
            UsageEvent.objects.filter(owner=request.user, created_at__gte=month_start)
            .values("category")
            .annotate(total=Count("id"))
        )
        usage_map = {item["category"]: item["total"] for item in usage}
        watchlist = []
        for symbol in ("BTCUSDT", "ETHUSDT"):
            try:
                watchlist.append({"symbol": symbol, "lastPrice": latest_price(symbol, "1h"), "changePct": 0})
            except ValueError:
                continue

        latest_runs = BacktestRun.objects.filter(owner=request.user).select_related("agent").prefetch_related("trades").order_by("-created_at")[:5]
        paper_account = account_snapshot(request.user)
        return Response(
            {
                "planName": "Founding Operator",
                "monthlyUsage": {
                    "backtests": usage_map.get("backtest", 0),
                    "aiMessages": usage_map.get("ai_message", 0),
                    "paperOrders": usage_map.get("paper_order", 0),
                },
                "liveTradingStatus": "coming_soon",
                "systemStatus": system_status(),
                "riskPolicy": {
                    **get_risk_policy(),
                    "currentOpenPositions": paper_account["riskPolicy"]["currentOpenPositions"],
                    "dailyRealizedLoss": paper_account["riskPolicy"]["dailyRealizedLoss"],
                },
                "dashboard": {
                    "latestBacktests": [serialize_backtest(run) for run in latest_runs],
                    "paperAccount": paper_account,
                    "watchlist": watchlist,
                    "defaultAgent": DEFAULT_AGENT,
                },
            }
        )
