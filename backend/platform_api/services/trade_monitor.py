import logging
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

from platform_api.models import Agent, TradeLog
from .alpaca_client import AlpacaAPIError, get_alpaca_client
from .market_data import format_display_symbol, latest_price, normalize_symbol

logger = logging.getLogger(__name__)


class TradeMonitorService:
    """
    Monitors and manages open positions with automated protections:
    - Trailing stop-loss orders (Alpaca native trailing_stop)
    - Break-even protection (moves stop to entry + buffer)
    - Take-profit limit orders
    - Partial profit taking (25%, 50%)
    - AI-assisted risk diagnosis & dynamic trailing adjustments
    """

    @classmethod
    def get_position_details(cls, symbol: str) -> dict[str, Any]:
        """
        Retrieves full position metrics, active Alpaca protective orders,
        breakeven benchmarks, and trailing stop recommendations.
        """
        client = get_alpaca_client()
        clean_sym = normalize_symbol(symbol)
        disp_sym = format_display_symbol(symbol)

        # 1. Fetch live position
        try:
            pos = client.get_position(clean_sym)
        except AlpacaAPIError:
            try:
                pos = client.get_position(disp_sym)
            except AlpacaAPIError as exc:
                return {"success": False, "error": f"Position not found: {exc}"}

        qty = float(pos.get("qty", 0.0))
        side = pos.get("side", "long").lower()
        avg_entry = float(pos.get("avg_entry_price", 0.0))
        current_px = float(pos.get("current_price", avg_entry))
        market_val = float(pos.get("market_value", 0.0))
        unrealized_pl = float(pos.get("unrealized_pl", 0.0))
        unrealized_plpc = float(pos.get("unrealized_plpc", 0.0)) * 100.0
        asset_class = pos.get("asset_class", "us_equity")

        # 2. Fetch active open orders for this symbol
        open_orders = client.get_orders(symbols=pos.get("symbol"), status="open")
        active_trailing_stop = None
        active_stop_loss = None
        active_take_profit = None

        for o in open_orders:
            o_type = o.get("type")
            if o_type == "trailing_stop":
                active_trailing_stop = {
                    "id": o.get("id"),
                    "trail_percent": float(o.get("trail_percent") or 0.0),
                    "trail_price": float(o.get("trail_price") or 0.0),
                    "stop_price": float(o.get("stop_price") or 0.0),
                    "hwm": float(o.get("hwm") or current_px),
                    "qty": float(o.get("qty") or qty),
                }
            elif o_type in ("stop", "stop_limit"):
                active_stop_loss = {
                    "id": o.get("id"),
                    "stop_price": float(o.get("stop_price") or 0.0),
                    "qty": float(o.get("qty") or qty),
                }
            elif o_type == "limit":
                active_take_profit = {
                    "id": o.get("id"),
                    "limit_price": float(o.get("limit_price") or 0.0),
                    "qty": float(o.get("qty") or qty),
                }

        is_protected = bool(active_trailing_stop or active_stop_loss)

        # 3. Calculate dynamic protection levels
        breakeven_price = round(avg_entry * (1.001 if side == "long" else 0.999), 2)
        
        # Trailing stop options based on current price
        trailing_presets = {
            "conservative_3pct": {
                "pct": 3.0,
                "stop_price": round(current_px * 0.97 if side == "long" else current_px * 1.03, 2),
                "guaranteed_pnl": round(((current_px * 0.97) - avg_entry) * qty if side == "long" else (avg_entry - (current_px * 1.03)) * qty, 2),
            },
            "balanced_5pct": {
                "pct": 5.0,
                "stop_price": round(current_px * 0.95 if side == "long" else current_px * 1.05, 2),
                "guaranteed_pnl": round(((current_px * 0.95) - avg_entry) * qty if side == "long" else (avg_entry - (current_px * 1.05)) * qty, 2),
            },
            "swing_8pct": {
                "pct": 8.0,
                "stop_price": round(current_px * 0.92 if side == "long" else current_px * 1.08, 2),
                "guaranteed_pnl": round(((current_px * 0.92) - avg_entry) * qty if side == "long" else (avg_entry - (current_px * 1.08)) * qty, 2),
            },
        }

        # Danger assessment: if in high profit without protection
        risk_alert = None
        if not is_protected and unrealized_plpc > 10.0:
            risk_alert = (
                f"HIGH RISK: Position is up {unrealized_plpc:.1f}% (+${unrealized_pl:,.2f}) with NO STOP LOSS. "
                f"A sudden market drawdown could erase your profits. Lock in break-even or activate a trailing stop."
            )
        elif not is_protected:
            risk_alert = "CAUTION: No stop-loss order is currently active for this position."

        return {
            "success": True,
            "symbol": pos.get("symbol"),
            "display_symbol": disp_sym,
            "asset_class": asset_class,
            "side": side,
            "qty": qty,
            "avg_entry_price": avg_entry,
            "current_price": current_px,
            "market_value": market_val,
            "unrealized_pnl": unrealized_pl,
            "unrealized_pnl_pct": round(unrealized_plpc, 2),
            "breakeven_price": breakeven_price,
            "is_protected": is_protected,
            "risk_alert": risk_alert,
            "active_protection": {
                "trailing_stop": active_trailing_stop,
                "stop_loss": active_stop_loss,
                "take_profit": active_take_profit,
            },
            "trailing_presets": trailing_presets,
        }

    @classmethod
    def apply_protection(
        cls,
        symbol: str,
        protect_type: str,  # "trailing_stop" | "stop_loss" | "breakeven" | "bracket"
        trail_percent: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict[str, Any]:
        """
        Cancels any existing stop/trailing orders on the position and applies the new protection.
        """
        client = get_alpaca_client()
        clean_sym = normalize_symbol(symbol)
        disp_sym = format_display_symbol(symbol)

        # 1. Look up position to determine size and side
        try:
            pos = client.get_position(clean_sym)
        except AlpacaAPIError:
            pos = client.get_position(disp_sym)

        qty = float(pos.get("qty", 0.0))
        side = pos.get("side", "long").lower()
        avg_entry = float(pos.get("avg_entry_price", 0.0))
        current_px = float(pos.get("current_price", avg_entry))
        alpaca_sym = pos.get("symbol")

        # Opposite side to exit the position
        exit_side = "sell" if side == "long" else "buy"

        # 2. Cancel ALL existing conflicting open orders for this symbol to free up position quantity
        existing_orders = client.get_orders(symbols=alpaca_sym, status="open")
        cancelled_orders = []
        for o in existing_orders:
            try:
                client.cancel_order(o["id"])
                cancelled_orders.append(o["id"])
            except Exception as exc:
                logger.warning(f"Could not cancel order {o['id']}: {exc}")

        placed_orders = []

        try:
            # 3. Apply requested protection
            if protect_type == "trailing_stop":
                pct = trail_percent or 5.0
                order_res = client._request(
                    "POST",
                    "/v2/orders",
                    data={
                        "symbol": alpaca_sym,
                        "qty": str(qty),
                        "side": exit_side,
                        "type": "trailing_stop",
                        "trail_percent": str(pct),
                        "time_in_force": "gtc",
                    },
                )
                placed_orders.append({"type": "trailing_stop", "trail_percent": pct, "id": order_res.get("id")})

            elif protect_type == "breakeven":
                # Set stop price slightly beyond entry to cover fees/spread
                be_price = round(avg_entry * (1.002 if side == "long" else 0.998), 2)
                order_res = client._request(
                    "POST",
                    "/v2/orders",
                    data={
                        "symbol": alpaca_sym,
                        "qty": str(qty),
                        "side": exit_side,
                        "type": "stop",
                        "stop_price": str(be_price),
                        "time_in_force": "gtc",
                    },
                )
                placed_orders.append({"type": "stop_loss", "stop_price": be_price, "id": order_res.get("id")})

            elif (protect_type == "bracket" or (stop_loss and take_profit)):
                # Use Alpaca OCO (One-Cancels-Other) so position quantity is shared
                sl_val = round(stop_loss, 2) if stop_loss else round(avg_entry, 2)
                tp_val = round(take_profit, 2) if take_profit else round(current_px * 1.10, 2)
                order_res = client._request(
                    "POST",
                    "/v2/orders",
                    data={
                        "symbol": alpaca_sym,
                        "qty": str(qty),
                        "side": exit_side,
                        "type": "limit",
                        "limit_price": str(tp_val),
                        "time_in_force": "gtc",
                        "order_class": "oco",
                        "take_profit": {"limit_price": str(tp_val)},
                        "stop_loss": {"stop_price": str(sl_val)},
                    },
                )
                placed_orders.append({"type": "oco_bracket", "stop_price": sl_val, "limit_price": tp_val, "id": order_res.get("id")})

            elif protect_type == "stop_loss" or stop_loss:
                sl_val = round(stop_loss, 2) if stop_loss else round(avg_entry, 2)
                order_res = client._request(
                    "POST",
                    "/v2/orders",
                    data={
                        "symbol": alpaca_sym,
                        "qty": str(qty),
                        "side": exit_side,
                        "type": "stop",
                        "stop_price": str(sl_val),
                        "time_in_force": "gtc",
                    },
                )
                placed_orders.append({"type": "stop_loss", "stop_price": sl_val, "id": order_res.get("id")})

            elif take_profit:
                tp_val = round(take_profit, 2)
                order_res = client._request(
                    "POST",
                    "/v2/orders",
                    data={
                        "symbol": alpaca_sym,
                        "qty": str(qty),
                        "side": exit_side,
                        "type": "limit",
                        "limit_price": str(tp_val),
                        "time_in_force": "gtc",
                    },
                )
                placed_orders.append({"type": "take_profit", "limit_price": tp_val, "id": order_res.get("id")})

            return {
                "success": True,
                "symbol": alpaca_sym,
                "protection_type": protect_type,
                "placed_orders": placed_orders,
                "cancelled_orders": cancelled_orders,
                "message": f"Protection successfully applied to {alpaca_sym}.",
            }
        except AlpacaAPIError as exc:
            logger.error(f"Alpaca protection error: {exc}")
            return {
                "success": False,
                "error": str(exc),
                "symbol": alpaca_sym,
                "placed_orders": placed_orders,
                "cancelled_orders": cancelled_orders,
            }

    @classmethod
    def close_partial(cls, symbol: str, percentage: Optional[float] = None, qty: Optional[float] = None) -> dict[str, Any]:
        """
        Closes a fraction of the open position (e.g. 25%, 50%) to bank profit.
        """
        client = get_alpaca_client()
        clean_sym = normalize_symbol(symbol)
        disp_sym = format_display_symbol(symbol)

        try:
            pos = client.get_position(clean_sym)
        except AlpacaAPIError:
            pos = client.get_position(disp_sym)

        total_qty = float(pos.get("qty", 0.0))
        target_qty = qty
        if percentage and not target_qty:
            target_qty = round(total_qty * (percentage / 100.0), 2)

        if not target_qty or target_qty <= 0 or target_qty > total_qty:
            return {"success": False, "error": f"Invalid partial quantity: {target_qty} of total {total_qty}"}

        # Use alpaca close_position with qty
        try:
            res = client.close_position(pos.get("symbol"), qty=target_qty)
            return {
                "success": True,
                "symbol": pos.get("symbol"),
                "closed_qty": target_qty,
                "remaining_qty": round(total_qty - target_qty, 2),
                "details": res,
            }
        except AlpacaAPIError as exc:
            return {"success": False, "error": str(exc)}

    @classmethod
    def get_ai_advice(cls, symbol: str) -> dict[str, Any]:
        """
        Generates tactical advice using Gemini AI to evaluate position risk,
        momentum, and optimal trailing stop settings.
        """
        details = cls.get_position_details(symbol)
        if not details.get("success"):
            return details

        # Try to call Gemini
        advice_text = ""
        suggested_trail_pct = 5.0
        suggested_stop_loss = details["trailing_presets"]["balanced_5pct"]["stop_price"]
        suggested_take_profit = round(details["current_price"] * 1.10, 2)

        try:
            from google import genai
            if settings.GEMINI_API_KEY:
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                prompt = (
                    f"You are the TradeFlow AI Guardian. Provide actionable trade management advice for an active open position.\n\n"
                    f"Position Details:\n"
                    f"- Symbol: {details['symbol']} ({details['asset_class']})\n"
                    f"- Side: {details['side'].upper()}\n"
                    f"- Size: {details['qty']} units\n"
                    f"- Entry Price: ${details['avg_entry_price']:,.2f}\n"
                    f"- Current Market Price: ${details['current_price']:,.2f}\n"
                    f"- Market Value: ${details['market_value']:,.2f}\n"
                    f"- Unrealized P&L: +${details['unrealized_pnl']:,.2f} (+{details['unrealized_pnl_pct']:.2f}%)\n"
                    f"- Active Protection: {'YES' if details['is_protected'] else 'NONE - AT RISK'}\n\n"
                    f"Task:\n"
                    f"1. Give a 2-sentence assessment of the current profit situation and risk of giveback.\n"
                    f"2. Explain why moving to Break-Even or activating a Trailing Stop protects capital without capping upside.\n"
                    f"3. Provide exact recommended actions: (A) Suggested Trailing Stop % (e.g., 5%), (B) Suggested Stop Loss Price, (C) Suggested Take-Profit Target."
                )
                response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                if getattr(response, "text", None):
                    advice_text = response.text
        except Exception as exc:
            logger.warning(f"AI advice generation error: {exc}")

        if not advice_text:
            advice_text = (
                f"Your position in {details['symbol']} is currently up +{details['unrealized_pnl_pct']}%, representing +${details['unrealized_pnl']:,.2f} in unrealized profit. "
                f"Because no protective order is attached, an abrupt market reversal could jeopardize these gains.\n\n"
                f"Recommendation:\n"
                f"1. Immediately activate an AI Trailing Stop at 5.0% (around ${suggested_stop_loss:,.2f}). This locks in over ${details['trailing_presets']['balanced_5pct']['guaranteed_pnl']:,.2f} in minimum profit while letting you participate in further upside.\n"
                f"2. Consider taking 25% or 50% partial profit off the table to reduce overall portfolio exposure."
            )

        return {
            "success": True,
            "symbol": details["symbol"],
            "details": details,
            "ai_advice": advice_text,
            "suggested_trail_percent": suggested_trail_pct,
            "suggested_stop_loss": suggested_stop_loss,
            "suggested_take_profit": suggested_take_profit,
            "breakeven_price": details["breakeven_price"],
        }
