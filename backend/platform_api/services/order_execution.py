import logging
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

from platform_api.models import Agent, TradeLog
from .alpaca_client import AlpacaAPIError, get_alpaca_client
from .market_data import format_display_symbol, latest_price, normalize_symbol
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)


class OrderExecutionService:
    """
    Coordinates order placement, modifications, position liquidation,
    risk management verification, and trade audit logging.
    """

    @classmethod
    def get_active_broker(cls) -> str:
        from platform_api.models import RiskRule
        import os
        rule = RiskRule.objects.filter(key="primary_broker").first()
        if rule and rule.value:
            if isinstance(rule.value, dict) and "value" in rule.value:
                return str(rule.value["value"]).lower()
            return str(rule.value).lower()
        return os.getenv("BROKER_PRIMARY", "alpaca").lower()

    @classmethod
    def set_active_broker(cls, broker: str) -> str:
        from platform_api.models import RiskRule
        broker_clean = broker.lower().strip()
        if broker_clean not in ("alpaca", "mt5"):
            broker_clean = "alpaca"
        rule, _ = RiskRule.objects.get_or_create(key="primary_broker")
        rule.value = {"value": broker_clean}
        rule.save()
        return broker_clean

    @classmethod
    def get_account_overview(cls) -> dict[str, Any]:
        """
        Fetches active broker metrics (Alpaca or MT5 Exness Demo/Cent).
        """
        active_broker = cls.get_active_broker()

        if active_broker == "mt5":
            from .mt5_client import get_mt5_client
            mt5_client = get_mt5_client()
            overview = mt5_client.get_account_overview()
            overview["active_broker"] = "mt5"
            return overview

        # Default: Alpaca
        client = get_alpaca_client()
        acc = client.get_account()
        mode = client.mode

        return {
            "broker": "alpaca",
            "active_broker": "alpaca",
            "brokerName": f"Alpaca {mode.capitalize()} Trading",
            "mode": mode,
            "account_id": acc.get("id"),
            "status": acc.get("status"),
            "currency": acc.get("currency", "USD"),
            "equity": float(acc.get("equity", 0.0)),
            "cash": float(acc.get("cash", 0.0)),
            "buying_power": float(acc.get("buying_power", 0.0)),
            "portfolio_value": float(acc.get("portfolio_value", 0.0)),
            "pattern_day_trader": acc.get("pattern_day_trader", False),
            "trading_blocked": acc.get("trading_blocked", False),
            "transfers_blocked": acc.get("transfers_blocked", False),
            "shorting_enabled": acc.get("shorting_enabled", True),
        }

    @classmethod
    def get_open_positions(cls) -> list[dict[str, Any]]:
        """
        Fetches all active open positions from the active broker, formatted with live P&L.
        """
        active_broker = cls.get_active_broker()
        if active_broker == "mt5":
            from .mt5_client import get_mt5_client
            return get_mt5_client().get_open_positions()

        client = get_alpaca_client()
        raw_positions = client.get_positions()
        formatted = []

        for p in raw_positions:
            sym = p.get("symbol", "")
            qty = float(p.get("qty", 0.0))
            avg_entry = float(p.get("avg_entry_price", 0.0))
            current_px = float(p.get("current_price", avg_entry))
            unrealized_pl = float(p.get("unrealized_pl", 0.0))
            unrealized_plpc = float(p.get("unrealized_plpc", 0.0)) * 100.0
            side = p.get("side", "long")

            formatted.append(
                {
                    "symbol": format_display_symbol(sym),
                    "raw_symbol": sym,
                    "qty": qty,
                    "side": side,
                    "avg_entry_price": avg_entry,
                    "current_price": current_px,
                    "market_value": float(p.get("market_value", 0.0)),
                    "cost_basis": float(p.get("cost_basis", 0.0)),
                    "unrealized_pnl": unrealized_pl,
                    "unrealized_pnl_pct": round(unrealized_plpc, 2),
                    "change_today": float(p.get("change_today", 0.0)),
                }
            )

        return formatted

    @classmethod
    def execute_order(
        cls,
        symbol: str,
        side: str,  # "buy" | "sell"
        qty: float,
        order_type: str = "market",  # "market" | "limit"
        limit_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        agent: Optional[Agent] = None,
        ai_reasoning: str = "",
        bypass_risk: bool = False,
    ) -> dict[str, Any]:
        """
        Executes a real order via Alpaca after validating through RiskManager.
        Logs the trade to TradeLog.
        """
        norm_sym = normalize_symbol(symbol)
        disp_sym = format_display_symbol(symbol)
        curr_price = limit_price or latest_price(norm_sym)

        # 1. Risk Evaluation
        if not bypass_risk:
            assessment = RiskManager.assess_order(
                symbol=disp_sym,
                side=side,
                qty=qty,
                current_price=curr_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            if not assessment["approved"]:
                logger.warning(f"Order rejected by RiskManager: {assessment['reason']}")
                return {
                    "success": False,
                    "error": assessment["reason"],
                    "risk_assessment": assessment,
                }
            # Adjust qty if suggested by risk manager
            if assessment.get("suggested_qty") and assessment["suggested_qty"] > 0:
                qty = assessment["suggested_qty"]
        else:
            assessment = {"approved": True, "reason": "Bypassed risk checks"}

        # 2. Submit to Active Broker
        if cls.get_active_broker() == "mt5":
            from .mt5_client import get_mt5_client
            mt5_client = get_mt5_client()
            is_crypto = any(c in norm_sym for c in ("BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB"))
            if is_crypto:
                vol = round(qty, 2)
                logged_qty = vol
            elif qty <= 10.0:
                vol = round(qty, 2)
                logged_qty = vol * 100000.0
            else:
                vol = round(qty / 100000.0, 2)
                logged_qty = qty

            if vol < 0.01:
                vol = 0.01
            mt5_res = mt5_client.execute_order(
                symbol=disp_sym,
                side=side,
                volume=vol,
                stop_loss=stop_loss,
                take_profit=take_profit,
                comment=f"TF {agent.name if agent else 'AI'}"[:31],
            )
            if not mt5_res.get("success"):
                return {
                    "success": False,
                    "broker": "MetaTrader 5 (Exness Demo)",
                    "error": mt5_res.get("error", "MT5 execution failed"),
                    "risk_assessment": assessment,
                }
            ticket = mt5_res.get("ticket")
            fill_price = float(mt5_res.get("entry_price") or curr_price)
            trade_log = TradeLog.objects.create(
                alpaca_order_id=f"MT5-{ticket}",
                agent=agent,
                symbol=disp_sym,
                side=side.lower(),
                qty=logged_qty,
                entry_price=fill_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                status="open",
                ai_reasoning=ai_reasoning or assessment.get("reason", ""),
                mode="mt5_demo",
            )
            return {
                "success": True,
                "broker": "MetaTrader 5 (Exness Demo)",
                "order_id": f"MT5-{ticket}",
                "ticket": ticket,
                "volume": vol,
                "trade_log_id": str(trade_log.id),
                "symbol": disp_sym,
                "side": side,
                "qty": vol * 100000.0,
                "entry_price": fill_price,
                "status": "filled",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_assessment": assessment,
                "mt5_response": mt5_res,
            }

        client = get_alpaca_client()

        # Submit to Alpaca
        try:
            alpaca_response = client.place_order(
                symbol=disp_sym,
                qty=qty,
                side=side,
                order_type=order_type,
                time_in_force="gtc",
                limit_price=limit_price,
                stop_loss_price=stop_loss,
                take_profit_price=take_profit,
            )
        except AlpacaAPIError as exc:
            # Fallback handling: in case of non-bracket allowed asset or pair formatting
            logger.warning(f"Primary order submission failed: {exc}. Retrying standard market/limit order...")
            try:
                alpaca_response = client.place_order(
                    symbol=disp_sym,
                    qty=qty,
                    side=side,
                    order_type=order_type,
                    time_in_force="gtc",
                    limit_price=limit_price,
                )
            except AlpacaAPIError as second_exc:
                logger.error(f"Alpaca order execution completely failed: {second_exc}")
                return {
                    "success": False,
                    "error": str(second_exc),
                    "risk_assessment": assessment,
                }

        order_id = alpaca_response.get("id")
        fill_price = float(alpaca_response.get("filled_avg_price") or curr_price)
        status = alpaca_response.get("status", "submitted")

        # 3. Log to database TradeLog
        trade_log = TradeLog.objects.create(
            alpaca_order_id=order_id,
            agent=agent,
            symbol=disp_sym,
            side=side.lower(),
            qty=qty,
            entry_price=fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            status="open" if status in {"filled", "partially_filled", "new", "accepted", "submitted"} else status,
            ai_reasoning=ai_reasoning or assessment.get("reason", ""),
            mode=client.mode,
        )

        return {
            "success": True,
            "order_id": order_id,
            "trade_log_id": str(trade_log.id),
            "symbol": disp_sym,
            "side": side,
            "qty": qty,
            "entry_price": fill_price,
            "status": status,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_assessment": assessment,
            "alpaca_order": alpaca_response,
        }

    @classmethod
    def _cancel_orders_for_symbol(cls, symbol: str) -> list[str]:
        """
        Cancel all open orders for a given symbol so that shares are freed
        from 'held_for_orders' before we attempt to close the position.
        Returns a list of cancelled order IDs.
        """
        client = get_alpaca_client()
        try:
            return client.cancel_orders_for_symbol(symbol)
        except Exception:
            return []

    @classmethod
    def close_position(cls, symbol: str, qty: Optional[float] = None) -> dict[str, Any]:
        """
        Liquidates an open position in Alpaca and updates TradeLog.

        Important: Alpaca returns HTTP 403 with code 40310000
        ("insufficient qty available") when open orders hold the shares.
        We must cancel those orders FIRST to free the shares, then close.
        """
        disp_sym = format_display_symbol(symbol)
        clean_sym = normalize_symbol(symbol)

        if cls.get_active_broker() == "mt5":
            from .mt5_client import get_mt5_client
            mt5_client = get_mt5_client()
            positions = mt5_client.get_open_positions()
            target_ticket = None
            if str(symbol).startswith("MT5-"):
                target_ticket = int(str(symbol).replace("MT5-", ""))
            elif str(symbol).isdigit():
                target_ticket = int(symbol)
            else:
                for p in positions:
                    pos_sym = p["symbol"].upper()
                    if clean_sym in pos_sym or pos_sym in clean_sym or pos_sym in (disp_sym, symbol.upper()):
                        target_ticket = p["ticket"]
                        break
            if not target_ticket and positions:
                target_ticket = positions[0]["ticket"]

            if target_ticket:
                close_res = mt5_client.close_position(target_ticket)
                # Update all matching open logs – TradeLog uses only exit_price (no exit_time field)
                TradeLog.objects.filter(
                    symbol=disp_sym, status="open"
                ).update(
                    status="closed",
                    exit_price=close_res.get("closed_price") or 0.0,
                )
                return close_res
            return {"success": False, "error": f"No open MT5 position found for {symbol}"}

        client = get_alpaca_client()

        # Step 1 – cancel any trailing-stop / stop-loss / bracket orders that
        # are holding shares so the DELETE /v2/positions request can proceed.
        cancelled_orders = cls._cancel_orders_for_symbol(clean_sym)
        if not cancelled_orders:
            # Also try the slash-format symbol (e.g. EUR/USD)
            cancelled_orders = cls._cancel_orders_for_symbol(disp_sym)

        # Give Alpaca a tiny moment to process the cancellations (non-blocking
        # markets may need this) – use a short sleep only if we cancelled something.
        if cancelled_orders:
            import time as _time
            _time.sleep(0.5)

        # Step 2 – close the position
        try:
            close_resp = client.close_position(clean_sym, qty=qty)
        except AlpacaAPIError as exc:
            # Try with slash format if unslashed failed
            try:
                close_resp = client.close_position(disp_sym, qty=qty)
            except Exception:
                return {
                    "success": False,
                    "error": str(exc),
                    "hint": (
                        "Alpaca rejected the close. "
                        f"Cancelled orders before attempt: {cancelled_orders}. "
                        "Check if there are still pending orders locking the shares."
                    ),
                }

        # Update open trade logs for this symbol
        open_trades = TradeLog.objects.filter(symbol=disp_sym, status="open")
        current_px = latest_price(clean_sym)
        for t in open_trades:
            t.status = "closed"
            t.exit_price = current_px
            if t.entry_price:
                # Realized P&L calculation
                multiplier = 1 if t.side.lower() == "buy" else -1
                t.realized_pnl = round((current_px - t.entry_price) * t.qty * multiplier, 2)
            t.save()

        return {
            "success": True,
            "symbol": disp_sym,
            "closed_at_price": current_px,
            "details": close_resp,
        }

    @classmethod
    def cancel_order(cls, order_id: str) -> dict[str, Any]:
        """
        Cancels a pending order in Alpaca.
        """
        client = get_alpaca_client()
        try:
            resp = client.cancel_order(order_id)
            TradeLog.objects.filter(alpaca_order_id=order_id).update(status="cancelled")
            return {"success": True, "order_id": order_id, "details": resp}
        except AlpacaAPIError as exc:
            return {"success": False, "error": str(exc)}

    @classmethod
    def get_trade_logs(cls, limit: int = 50) -> list[dict[str, Any]]:
        """
        Retrieves internal trade audit history.
        """
        logs = TradeLog.objects.all().order_by("-created_at")[:limit]
        return [
            {
                "id": str(t.id),
                "alpaca_order_id": t.alpaca_order_id,
                "agent_id": str(t.agent.id) if t.agent else None,
                "agent_name": t.agent.name if t.agent else "Manual/Direct",
                "symbol": t.symbol,
                "side": t.side,
                "qty": t.qty,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "stop_loss": t.stop_loss,
                "take_profit": t.take_profit,
                "realized_pnl": t.realized_pnl,
                "status": t.status,
                "ai_reasoning": t.ai_reasoning,
                "mode": t.mode,
                "created_at": t.created_at.isoformat(),
            }
            for t in logs
        ]
