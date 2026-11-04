import logging
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

from platform_api.models import Agent, TradeLog
from .alpaca_client import AlpacaAPIError, get_alpaca_client
from .market_data import SYNTHETIC_SOURCE, candle_data_source, format_display_symbol, get_candles, latest_price, normalize_symbol
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
        signal_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Executes a real order after validating through RiskManager.
        AI/auto paths must pass signal_id so TradeLog links to AISignal.
        bypass_risk is manual-desk only and is loudly logged.
        """
        norm_sym = normalize_symbol(symbol)
        disp_sym = format_display_symbol(symbol)
        strategy_version = "trend-breakout-v1/1.0.0" if signal_id else "manual/direct"

        # A demo price must never be allowed to route an order. This applies to
        # manual, AI-assisted, and autonomous paths alike.
        try:
            market_candles = get_candles(norm_sym, timeframe="1m", limit=2)
        except ValueError as exc:
            return {"success": False, "error": f"Order rejected: {exc}"}
        if candle_data_source(market_candles) == SYNTHETIC_SOURCE:
            return {
                "success": False,
                "error": "Order rejected: current market data is synthetic demo data, not a broker/provider quote.",
            }
        curr_price = limit_price or float(market_candles[-1]["close"])

        # 1b. Journal snapshot (best-effort, never blocks the order).
        journal = cls._journal_snapshot(disp_sym)

        # 1. Risk Evaluation (AI is narrator/watchdog: it can never bypass this).
        if bypass_risk:
            logger.warning("Order bypass_risk=True (manual desk only): %s %s qty=%s", symbol, side, qty)
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
                strategy_version=strategy_version,
                regime=journal.get("regime", ""),
                votes=journal.get("votes", {}),
                session=journal.get("session", ""),
                news_state=journal.get("news_state", ""),
                spread_pips=journal.get("spread_pips"),
            )
            cls._link_signal(signal_id, trade_log)
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
            strategy_version=strategy_version,
            regime=journal.get("regime", ""),
            votes=journal.get("votes", {}),
            session=journal.get("session", ""),
            news_state=journal.get("news_state", ""),
            spread_pips=journal.get("spread_pips"),
        )
        cls._link_signal(signal_id, trade_log)

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
    def _journal_snapshot(cls, disp_sym: str) -> dict:
        """Best-effort regime/votes/session/news/spread at fill time. Never raises."""
        snap: dict = {"regime": "", "votes": {}, "session": "", "news_state": "", "spread_pips": None}
        try:
            from .economic_calendar import EconomicCalendarService
            from .market_data import get_forex_quote
            from .multi_timeframe import MultiTimeframeService
            from .session_filter import SessionFilterService

            mtf = MultiTimeframeService.analyze_top_down(disp_sym)
            snap["regime"] = mtf.get("macro_bias_4h", "")
            snap["votes"] = {
                "quality": mtf.get("confluence_quality"),
                "score": mtf.get("composite_score"),
                "side": mtf.get("suggested_side"),
                "h1": mtf.get("h1", {}).get("direction"),
                "m15": mtf.get("m15", {}).get("direction"),
            }
            blocked, _, _ = EconomicCalendarService.is_news_blocked(disp_sym)
            snap["news_state"] = "BLOCKED" if blocked else "CLEAR"
            snap["session"] = SessionFilterService.get_current_session_info().get("primary_session", "")
            snap["spread_pips"] = get_forex_quote(disp_sym).get("spread_pips")
        except Exception as exc:
            logger.warning("Journal snapshot failed for %s: %s", disp_sym, exc)
        return snap

    @classmethod
    def _excursion_for_trade(cls, trade) -> dict:
        """MFE/MAE in R from entry to now using 1h bars. Best-effort."""
        try:
            from .market_data import get_candles, normalize_symbol

            if not trade.entry_price or not trade.stop_loss:
                return {}
            sl_dist = abs(trade.entry_price - trade.stop_loss)
            if sl_dist <= 0:
                return {}
            candles = get_candles(normalize_symbol(trade.symbol), timeframe="1h", limit=500)
            bars = [c for c in candles if c.get("time", "") >= trade.created_at.isoformat()]
            if not bars:
                bars = candles[-24:]
            if trade.side.lower() == "buy":
                mfe = max(float(b["high"]) - trade.entry_price for b in bars)
                mae = min(float(b["low"]) - trade.entry_price for b in bars)
            else:
                mfe = max(trade.entry_price - float(b["low"]) for b in bars)
                mae = min(trade.entry_price - float(b["high"]) for b in bars)
            return {"mfe_r": round(mfe / sl_dist, 2), "mae_r": round(mae / sl_dist, 2)}
        except Exception as exc:
            logger.warning("Excursion calc failed for trade %s: %s", getattr(trade, "id", "?"), exc)
            return {}

    @classmethod
    def review_trade(cls, trade_id: str, followed_plan=None, lesson_tag: str = "", human_note: str = "") -> dict:
        from platform_api.models import LESSON_TAG_CHOICES

        allowed = {c[0] for c in LESSON_TAG_CHOICES}
        trade = TradeLog.objects.filter(id=trade_id).first()
        if not trade:
            return {"success": False, "error": "Trade not found."}
        if lesson_tag and lesson_tag not in allowed:
            return {"success": False, "error": f"Invalid lesson_tag. Allowed: {sorted(allowed)}"}
        if followed_plan is not None:
            trade.followed_plan = bool(followed_plan)
        if lesson_tag:
            trade.lesson_tag = lesson_tag
        if human_note:
            trade.human_note = human_note[:140]
        trade.save()
        return {"success": True, "id": str(trade.id)}

    @classmethod
    def _link_signal(cls, signal_id: Optional[str], trade_log) -> None:
        if not signal_id:
            return
        try:
            from platform_api.models import AISignal

            sig = AISignal.objects.filter(id=signal_id).first()
            if sig:
                sig.acted_on = True
                sig.trade_log = trade_log
                sig.save(update_fields=["acted_on", "trade_log", "updated_at"])
        except Exception as exc:
            logger.warning("Could not link signal %s to trade %s: %s", signal_id, trade_log.id, exc)

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
    def close_position(cls, symbol: str, qty: Optional[float] = None, exit_reason: str = "manual") -> dict[str, Any]:
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
                if not close_res.get("success"):
                    return close_res
                # Match the closed broker ticket so other positions in the
                # same pair remain open in the audit journal.
                mt5_order_id = f"MT5-{target_ticket}"
                for t in TradeLog.objects.filter(alpaca_order_id=mt5_order_id, status="open"):
                    t.status = "closed"
                    t.exit_price = close_res.get("closed_price") or 0.0
                    t.realized_pnl = close_res.get("profit")
                    t.fee_paid = close_res.get("fee_paid")
                    t.pnl_source = close_res.get("pnl_source", "unknown")
                    t.exit_reason = exit_reason
                    t.closed_at = timezone.now()
                    exc = cls._excursion_for_trade(t)
                    if exc:
                        t.mfe_r = exc.get("mfe_r")
                        t.mae_r = exc.get("mae_r")
                    t.save()
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

        # Update open trade logs for this symbol (same row, no duplicate leg).
        open_trades = TradeLog.objects.filter(symbol=disp_sym, status="open")
        current_px = latest_price(clean_sym)
        fill_price = None
        if isinstance(close_resp, dict):
            raw_fill = close_resp.get("filled_avg_price") or close_resp.get("avg_fill_price")
            if raw_fill is not None:
                try:
                    fill_price = float(raw_fill)
                except (TypeError, ValueError):
                    fill_price = None
        if fill_price is not None:
            current_px = fill_price
        for t in open_trades:
            t.status = "closed"
            t.exit_price = current_px
            t.exit_reason = exit_reason
            t.closed_at = timezone.now()
            t.pnl_source = "broker_fill" if fill_price is not None else "quote_estimate"
            if t.entry_price:
                # Realized P&L calculation
                multiplier = 1 if t.side.lower() == "buy" else -1
                t.realized_pnl = round((current_px - t.entry_price) * t.qty * multiplier, 2)
            exc = cls._excursion_for_trade(t)
            if exc:
                t.mfe_r = exc.get("mfe_r")
                t.mae_r = exc.get("mae_r")
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
                "pnl_source": t.pnl_source,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                "status": t.status,
                "ai_reasoning": t.ai_reasoning,
                "mode": t.mode,
                "created_at": t.created_at.isoformat(),
                "strategy_version": t.strategy_version,
                "regime": t.regime,
                "votes": t.votes,
                "session": t.session,
                "news_state": t.news_state,
                "spread_pips": t.spread_pips,
                "fee_paid": t.fee_paid,
                "mfe_r": t.mfe_r,
                "mae_r": t.mae_r,
                "exit_reason": t.exit_reason,
                "followed_plan": t.followed_plan,
                "lesson_tag": t.lesson_tag,
                "human_note": t.human_note,
            }
            for t in logs
        ]

    @classmethod
    def sync_closed_mt5_trade_logs(cls) -> dict[str, Any]:
        """Reconcile MT5 SL/TP/manual closes that happened outside the app."""
        from . import mt5_client as mt5_adapter
        from .mt5_client import MT5_AVAILABLE, get_mt5_client

        client = get_mt5_client()
        if not MT5_AVAILABLE or not client.is_connected():
            return {"connected": False, "synced": 0}

        positions = mt5_adapter.mt5.positions_get()
        if positions is None:
            return {"connected": True, "synced": 0, "complete": False}
        open_tickets = {
            int(position_id)
            for position in positions
            for position_id in (getattr(position, "ticket", None), getattr(position, "identifier", None))
            if position_id is not None
        }
        synced = 0
        for trade in TradeLog.objects.filter(mode="mt5_demo", status="open"):
            try:
                ticket = int((trade.alpaca_order_id or "").removeprefix("MT5-"))
            except (TypeError, ValueError):
                continue
            if ticket in open_tickets:
                continue
            result = client.get_closed_position_summary(ticket)
            if not result:
                continue
            trade.status = "closed"
            trade.exit_price = result["closed_price"]
            trade.realized_pnl = result["profit"]
            trade.fee_paid = result["fee_paid"]
            trade.pnl_source = result["pnl_source"]
            trade.exit_reason = result["exit_reason"]
            trade.closed_at = result["closed_at"]
            exc = cls._excursion_for_trade(trade)
            if exc:
                trade.mfe_r = exc.get("mfe_r")
                trade.mae_r = exc.get("mae_r")
            trade.save()
            synced += 1

        return {"connected": True, "synced": synced, "complete": True}
