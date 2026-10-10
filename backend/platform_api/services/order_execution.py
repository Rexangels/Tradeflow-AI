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
    def get_account_overview(cls) -> dict[str, Any]:
        """
        Fetches current Alpaca account metrics and active mode.
        """
        client = get_alpaca_client()
        acc = client.get_account()
        mode = client.mode

        return {
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
        Fetches all active open positions from Alpaca, formatted with live P&L.
        """
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

        client = get_alpaca_client()

        # 2. Submit to Alpaca
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
    def close_position(cls, symbol: str, qty: Optional[float] = None) -> dict[str, Any]:
        """
        Liquidates an open position in Alpaca and updates TradeLog.
        """
        client = get_alpaca_client()
        disp_sym = format_display_symbol(symbol)
        clean_sym = normalize_symbol(symbol)

        try:
            close_resp = client.close_position(clean_sym, qty=qty)
        except AlpacaAPIError as exc:
            # Try with slash format if unslashed failed
            try:
                close_resp = client.close_position(disp_sym, qty=qty)
            except Exception:
                return {"success": False, "error": str(exc)}

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
