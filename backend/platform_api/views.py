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
from .models import Agent, BacktestRun, BacktestTrade, ChatMessage, ChatThread, MarketDataSnapshot, UsageEvent
from .permissions import IsTradeflowAdmin
from .presenters import serialize_agent, serialize_backtest, serialize_market_data_snapshot
from .serializers import (
    AgentPayloadSerializer,
    AiChatSerializer,
    BacktestRequestSerializer,
    LoginSerializer,
    MarketDataQuerySerializer,
    MarketDataFeaturesQuerySerializer,
    PaperOrderSerializer,
)
from .services.ai_orchestrator import handle_chat
from .services.backtests import run_backtest, trade_timestamp
from .services.market_data import candle_data_source, get_candles, latest_price, market_data_quality_report, normalize_symbol
from .services.market_data_snapshots import create_market_data_snapshot
from .services.feature_engine import build_feature_series
from .services.regime_classifier import classify_regime_series
from .services.strategy_registry import list_strategy_definitions, strategy_contract_for
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


class StrategyCatalogView(APIView):
    """Read-only catalogue of research strategies and their declared limits."""

    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        return Response(list_strategy_definitions())


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


class MarketDataFeaturesView(APIView):
    """Return deterministic, versioned, causal features for historical candles."""

    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        serializer = MarketDataFeaturesQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            candles = get_candles(
                payload["symbol"],
                payload["timeframe"],
                limit=payload["limit"],
                force_refresh=payload["forceRefresh"],
            )
            features = build_feature_series(
                candles,
                symbol=normalize_symbol(payload["symbol"]),
                timeframe=payload["timeframe"],
                spread_pips=payload.get("spreadPips"),
                pip_size=payload.get("pipSize"),
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        features["regime"] = classify_regime_series(features)
        return Response(features)


class MarketDataStatusView(APIView):
    """Read-only verification of the data used for a market symbol.

    This lets the UI prove the current provider and last bar before a user
    relies on analysis. It intentionally never returns provider credentials.
    """
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        symbol = request.query_params.get("symbol", "EUR/USD")
        timeframe = request.query_params.get("timeframe", "1h")
        try:
            candles = get_candles(symbol, timeframe, limit=2, force_refresh=True)
        except ValueError as exc:
            return Response({
                "available": False,
                "symbol": symbol.upper(),
                "timeframe": timeframe,
                "error": str(exc),
            })

        source = candle_data_source(candles)
        latest = candles[-1] if candles else None
        quality = market_data_quality_report(candles, timeframe) if candles else None
        return Response({
            "available": bool(latest),
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "source": source,
            "isRealData": source in {"mt5", "alpaca"},
            "latestBarTime": latest.get("time") if latest else None,
            "checkedAt": timezone.now().isoformat(),
            "quality": quality,
        })


class MarketDataSnapshotsView(APIView):
    """List saved research datasets belonging to the authenticated operator."""

    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        queryset = MarketDataSnapshot.objects.filter(owner=request.user)
        symbol = request.query_params.get("symbol")
        timeframe = request.query_params.get("timeframe")
        if symbol:
            queryset = queryset.filter(symbol=normalize_symbol(symbol))
        if timeframe:
            queryset = queryset.filter(timeframe=timeframe)

        try:
            limit = int(request.query_params.get("limit", "20"))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"limit": "Must be an integer between 1 and 100."}) from exc
        if not 1 <= limit <= 100:
            raise ValidationError({"limit": "Must be an integer between 1 and 100."})

        snapshots = queryset.order_by("-retrieved_at")[:limit]
        return Response([serialize_market_data_snapshot(item) for item in snapshots])


class MarketDataSnapshotDetailView(APIView):
    """Return a saved dataset and exact candle payload, scoped to its owner."""

    permission_classes = [IsTradeflowAdmin]

    def get(self, request, snapshot_id):
        snapshot = MarketDataSnapshot.objects.filter(
            id=snapshot_id,
            owner=request.user,
        ).first()
        if snapshot is None:
            return Response({"detail": "Market data snapshot not found."}, status=404)
        return Response(serialize_market_data_snapshot(snapshot, include_candles=True))


class BacktestsView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        runs = BacktestRun.objects.filter(owner=request.user).select_related("agent", "snapshot").prefetch_related("trades").order_by("-created_at")[:20]
        return Response([serialize_backtest(run) for run in runs])

    @transaction.atomic
    def post(self, request):
        serializer = BacktestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        supplied_candles = payload.get("candles")
        candles = (
            supplied_candles
            if supplied_candles is not None
            else get_candles(payload["symbol"], payload["timeframe"], limit=payload.get("limit", 500))
        )
        try:
            # Resolve and validate the selected strategies before persisting a
            # dataset, so an invalid engine mix cannot leave an orphan snapshot.
            strategy_contract_for(payload["agent"])
            snapshot = create_market_data_snapshot(
                request.user,
                payload["symbol"],
                payload["timeframe"],
                candles,
                metadata={
                    "origin": "request_supplied" if supplied_candles is not None else "provider_fetch",
                    "requested_limit": payload.get("limit", len(candles)),
                },
            )
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
            snapshot=snapshot,
            validation={
                **result["validation"],
                "walkForward": result["walkForward"],
                "modelAnalysis": result["modelAnalysis"],
                "strategyContract": result.get("strategyContract"),
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
        run = BacktestRun.objects.select_related("agent", "snapshot").prefetch_related("trades").get(id=run.id)
        return Response(serialize_backtest(run), status=201)


class BacktestDetailView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request, backtest_id):
        run = BacktestRun.objects.select_related("agent", "snapshot").prefetch_related("trades").get(id=backtest_id, owner=request.user)
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

    def _serialize_messages(self, thread: "ChatThread"):
        msgs = thread.messages.order_by("created_at")
        return [
            {"id": str(m.id), "role": m.role, "content": m.content}
            for m in msgs
            if m.role != "tool"  # skip raw tool-context noise from history
        ]

    def get(self, request):
        """Return the latest thread + its full message history for this user."""
        thread_id = request.query_params.get("threadId")
        if thread_id:
            try:
                thread = ChatThread.objects.get(id=thread_id, owner=request.user)
            except ChatThread.DoesNotExist:
                return Response({"threadId": None, "messages": []})
        else:
            thread = (
                ChatThread.objects.filter(owner=request.user)
                .order_by("-created")
                .first()
            )
        if not thread:
            return Response({"threadId": None, "messages": []})

        # Return all messages including tool ones so the UI can render context
        all_msgs = thread.messages.order_by("created_at")
        messages = [
            {"id": str(m.id), "role": m.role, "content": m.content}
            for m in all_msgs
        ]
        return Response({"threadId": str(thread.id), "title": thread.title, "messages": messages})

    def post(self, request):
        serializer = AiChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(handle_chat(request.user, serializer.validated_data))

    def delete(self, request):
        """Mark a thread as ended (or delete it), returning a clean slate."""
        thread_id = request.query_params.get("threadId")
        if thread_id:
            ChatThread.objects.filter(id=thread_id, owner=request.user).delete()
        return Response({"threadId": None, "messages": []})


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
