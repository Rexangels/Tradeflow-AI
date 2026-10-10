import logging
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from .models import Agent, ForexPairConfig, RiskRule, TradeLog
from .permissions import IsTradeflowAdmin
from .services.alpaca_client import get_alpaca_client
from .services.market_data import (
    format_display_symbol,
    get_candles,
    get_forex_quote,
    latest_price,
    normalize_symbol,
)
from .services.order_execution import OrderExecutionService
from .services.risk_manager import RiskManager


class ForexPairsView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        configs = ForexPairConfig.objects.all().order_by("symbol")
        result = []
        for cfg in configs:
            try:
                quote = get_forex_quote(cfg.symbol)
            except Exception:
                quote = {"bid": 0.0, "ask": 0.0, "mid": 0.0, "spread_pips": 0.0}

            result.append(
                {
                    "id": str(cfg.id),
                    "symbol": cfg.symbol,
                    "normalizedSymbol": normalize_symbol(cfg.symbol),
                    "isWatched": cfg.is_watched,
                    "defaultQty": cfg.default_qty or 1000.0,
                    "notes": cfg.notes,
                    "quote": quote,
                }
            )
        return Response(result)

    def post(self, request):
        symbol = request.data.get("symbol", "").strip()
        if not symbol:
            raise ValidationError({"symbol": "Symbol is required."})

        disp_sym = format_display_symbol(symbol)
        pair, created = ForexPairConfig.objects.get_or_create(
            symbol=disp_sym,
            defaults={
                "is_watched": request.data.get("isWatched", True),
                "default_qty": request.data.get("defaultQty", 1000.0),
                "notes": request.data.get("notes", ""),
            },
        )
        if not created:
            pair.is_watched = request.data.get("isWatched", pair.is_watched)
            pair.default_qty = request.data.get("defaultQty", pair.default_qty)
            pair.notes = request.data.get("notes", pair.notes)
            pair.save()

        return Response(
            {
                "id": str(pair.id),
                "symbol": pair.symbol,
                "isWatched": pair.is_watched,
                "defaultQty": pair.default_qty,
            },
            status=201,
        )


class ForexPairDetailView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def put(self, request, symbol):
        disp_sym = format_display_symbol(symbol)
        pair = ForexPairConfig.objects.filter(symbol=disp_sym).first()
        if not pair:
            return Response({"detail": "Pair not found."}, status=404)

        if "isWatched" in request.data:
            pair.is_watched = bool(request.data["isWatched"])
        if "defaultQty" in request.data:
            pair.default_qty = float(request.data["defaultQty"])
        if "notes" in request.data:
            pair.notes = str(request.data["notes"])
        pair.save()

        return Response(
            {
                "id": str(pair.id),
                "symbol": pair.symbol,
                "isWatched": pair.is_watched,
                "defaultQty": pair.default_qty,
                "notes": pair.notes,
            }
        )

    def delete(self, request, symbol):
        disp_sym = format_display_symbol(symbol)
        ForexPairConfig.objects.filter(symbol=disp_sym).delete()
        return Response({"status": "deleted", "symbol": disp_sym})


class ForexQuoteView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, symbol):
        quote = get_forex_quote(symbol)
        return Response(quote)


class ActiveBrokerView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        from .services.mt5_client import get_mt5_client
        active = OrderExecutionService.get_active_broker()
        mt5_overview = get_mt5_client().get_account_overview()
        alpaca_client = get_alpaca_client()
        alpaca_acc = alpaca_client.get_account()

        return Response({
            "activeBroker": active,
            "brokers": {
                "alpaca": {
                    "name": "Alpaca Securities",
                    "mode": alpaca_client.mode,
                    "connected": True,
                    "equity": float(alpaca_acc.get("equity", 0.0)),
                    "supportedAssets": ["US Stocks", "Crypto", "ETFs"],
                },
                "mt5": {
                    "name": "Exness MetaTrader 5",
                    "login": mt5_overview.get("accountNumber", "477536967"),
                    "server": mt5_overview.get("brokerName", "Exness-MT5Trial9"),
                    "currency": mt5_overview.get("currency", "USC"),
                    "isCentAccount": mt5_overview.get("isCentAccount", True),
                    "balance": mt5_overview.get("balance", 15.0),
                    "connected": mt5_overview.get("connected", False),
                    "statusNote": mt5_overview.get("statusNote"),
                    "supportedAssets": ["Spot Forex (EUR/USD, GBP/USD)", "Gold (XAU/USD)", "Indices"],
                },
            },
        })

    def post(self, request):
        broker = request.data.get("broker", "alpaca")
        set_broker = OrderExecutionService.set_active_broker(broker)
        return Response({"activeBroker": set_broker, "status": "updated"})


class TradingAccountView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        overview = OrderExecutionService.get_account_overview()
        positions = OrderExecutionService.get_open_positions()
        total_unrealized = sum(p.get("unrealized_pnl", 0.0) for p in positions)

        return Response(
            {
                **overview,
                "openPositionsCount": len(positions),
                "totalUnrealizedPnl": round(total_unrealized, 2),
                "riskRules": RiskManager.get_all_rules(),
            }
        )


class TradingPositionsView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        positions = OrderExecutionService.get_open_positions()
        return Response(positions)


class TradingPositionDetailView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request, symbol):
        from .services.trade_monitor import TradeMonitorService

        details = TradeMonitorService.get_position_details(symbol)
        if not details.get("success"):
            return Response(details, status=404)
        return Response(details)

    def post(self, request, symbol):
        from .services.trade_monitor import TradeMonitorService

        action = request.data.get("action", "protect")

        try:
            if action == "ai_advise":
                res = TradeMonitorService.get_ai_advice(symbol)
                return Response(res)

            elif action == "close_partial":
                percentage = request.data.get("percentage")
                qty = request.data.get("qty")
                parsed_pct = float(percentage) if percentage is not None else None
                parsed_qty = float(qty) if qty is not None else None
                res = TradeMonitorService.close_partial(symbol, percentage=parsed_pct, qty=parsed_qty)
                if not res.get("success"):
                    return Response(res, status=400)
                return Response(res)

            elif action == "protect":
                protect_type = request.data.get("protect_type", "trailing_stop")
                trail_pct = request.data.get("trail_percent")
                stop_loss = request.data.get("stop_loss")
                take_profit = request.data.get("take_profit")

                parsed_trail = float(trail_pct) if trail_pct is not None else None
                parsed_sl = float(stop_loss) if stop_loss is not None else None
                parsed_tp = float(take_profit) if take_profit is not None else None

                res = TradeMonitorService.apply_protection(
                    symbol=symbol,
                    protect_type=protect_type,
                    trail_percent=parsed_trail,
                    stop_loss=parsed_sl,
                    take_profit=parsed_tp,
                )
                if not res.get("success"):
                    return Response(res, status=400)
                return Response(res)

            return Response({"error": f"Unknown action: {action}"}, status=400)
        except Exception as exc:
            logger.error(f"Error handling position action {action} for {symbol}: {exc}", exc_info=True)
            return Response({"success": False, "error": str(exc)}, status=400)

    def delete(self, request, symbol):
        qty = request.query_params.get("qty")
        parsed_qty = float(qty) if qty else None
        res = OrderExecutionService.close_position(symbol, qty=parsed_qty)
        if not res.get("success"):
            return Response(res, status=400)
        return Response(res)



class TradingOrdersView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        limit = int(request.query_params.get("limit", 50))
        logs = OrderExecutionService.get_trade_logs(limit=limit)
        return Response(logs)

    def post(self, request):
        data = request.data
        symbol = data.get("symbol")
        side = data.get("side")
        qty = data.get("qty")

        if not symbol or not side or not qty:
            raise ValidationError({"detail": "symbol, side, and qty are required fields."})

        agent = None
        agent_id = data.get("agent_id")
        if agent_id:
            agent = Agent.objects.filter(id=agent_id, owner=request.user).first()

        res = OrderExecutionService.execute_order(
            symbol=symbol,
            side=side,
            qty=float(qty),
            order_type=data.get("order_type", "market"),
            limit_price=float(data["limit_price"]) if data.get("limit_price") else None,
            stop_loss=float(data["stop_loss"]) if data.get("stop_loss") else None,
            take_profit=float(data["take_profit"]) if data.get("take_profit") else None,
            agent=agent,
            ai_reasoning=data.get("ai_reasoning", "Manual platform execution"),
            bypass_risk=bool(data.get("bypass_risk", False)),
        )

        if not res.get("success"):
            return Response(res, status=400)
        return Response(res, status=201)


class TradingOrderDetailView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def delete(self, request, order_id):
        res = OrderExecutionService.cancel_order(order_id)
        if not res.get("success"):
            return Response(res, status=400)
        return Response(res)


class RiskRulesView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        rules = RiskManager.get_all_rules()
        return Response(rules)

    def put(self, request):
        updates = request.data
        if not isinstance(updates, dict):
            raise ValidationError({"detail": "Expected a key-value dictionary of rules."})

        updated = {}
        for k, v in updates.items():
            rule = RiskManager.update_rule(k, v)
            updated[k] = v

        return Response({"status": "updated", "rules": RiskManager.get_all_rules()})


class RiskCheckView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def post(self, request):
        data = request.data
        symbol = data.get("symbol")
        side = data.get("side", "buy")
        qty = float(data.get("qty", 1000.0))
        current_price = float(data.get("current_price") or latest_price(symbol or "EURUSD"))
        stop_loss = float(data["stop_loss"]) if data.get("stop_loss") else None
        take_profit = float(data["take_profit"]) if data.get("take_profit") else None

        assessment = RiskManager.assess_order(
            symbol=symbol or "EUR/USD",
            side=side,
            qty=qty,
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        return Response(assessment)


class AgentCycleView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def post(self, request):
        from .services.ai_orchestrator import run_agent_cycle

        agent_id = request.data.get("agent_id")
        agent = Agent.objects.filter(id=agent_id, owner=request.user).first() if agent_id else Agent.objects.filter(owner=request.user).first()
        symbol = request.data.get("symbol")
        auto_trade = bool(request.data.get("auto_trade", False))

        report = run_agent_cycle(request.user, agent=agent, symbol=symbol, auto_trade=auto_trade)
        return Response(report)


class AISignalsView(APIView):
    permission_classes = [IsTradeflowAdmin]

    def get(self, request):
        from platform_api.models import AISignal

        signals = AISignal.objects.all().select_related("agent", "trade_log").order_by("-created_at")[:50]
        data = [
            {
                "id": str(s.id),
                "agentName": s.agent.name if s.agent else "Strategy Agent",
                "symbol": s.symbol,
                "timeframe": s.timeframe,
                "direction": s.direction,
                "confidence": s.confidence,
                "confidencePct": round(s.confidence * 100.0, 1),
                "reasoning": s.reasoning,
                "indicators": s.indicators,
                "actedOn": s.acted_on,
                "tradeLogId": str(s.trade_log.id) if s.trade_log else None,
                "createdAt": s.created_at.isoformat(),
            }
            for s in signals
        ]
        return Response(data)


class EconomicCalendarView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from .services.economic_calendar import EconomicCalendarService

        symbol = request.query_params.get("symbol")
        events = EconomicCalendarService.get_upcoming_events(hours_ahead=24)
        shield_status = None
        if symbol:
            is_blocked, reason, ev = EconomicCalendarService.is_news_blocked(symbol)
            shield_status = {"symbol": symbol, "is_blocked": is_blocked, "reason": reason, "event": ev}
        return Response({"events": events, "shield_status": shield_status})


class TradingSessionsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        from .services.session_filter import SessionFilterService

        info = SessionFilterService.get_current_session_info()
        return Response(info)


class MultiTimeframeConfluenceView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, symbol):
        from .services.multi_timeframe import MultiTimeframeService

        result = MultiTimeframeService.analyze_top_down(symbol)
        return Response(result)

