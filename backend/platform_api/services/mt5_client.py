from __future__ import annotations

import logging
import math
import os
import time
from datetime import datetime, timezone as dt_timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

from .market_data import format_display_symbol

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False


def normalise_mt5_volume(requested_volume: float, symbol_info: Any = None) -> float:
    """Return a broker-valid volume rounded DOWN; never upscale to a minimum lot."""
    requested = float(requested_volume)
    if not math.isfinite(requested) or requested <= 0:
        raise ValueError("requested volume must be a finite positive number")
    minimum = float(getattr(symbol_info, "volume_min", 0.0) or 0.0) if symbol_info else 0.0
    maximum = float(getattr(symbol_info, "volume_max", 0.0) or 0.0) if symbol_info else 0.0
    step = float(getattr(symbol_info, "volume_step", 0.0) or 0.0) if symbol_info else 0.0
    if minimum > 0 and requested + 1e-12 < minimum:
        raise ValueError(f"requested volume {requested:g} is below broker minimum {minimum:g}; risk budget cannot be increased")
    if maximum > 0 and requested > maximum + 1e-12:
        raise ValueError(f"requested volume {requested:g} exceeds broker maximum {maximum:g}")
    final_volume = requested
    if step > 0:
        final_volume = math.floor((requested + 1e-12) / step) * step
    if minimum > 0 and final_volume + 1e-12 < minimum:
        raise ValueError(f"volume step would reduce the order below broker minimum {minimum:g}")
    if final_volume <= 0:
        raise ValueError("requested volume is too small for the broker volume step")
    return round(final_volume, 8)


class MT5Client:
    """
    Institutional MetaTrader 5 Gateway for Exness Demo and Cent Accounts.
    Enables micro-lot order routing, zero-latency price streams, and broker-side
    trailing stops directly through the MetaTrader 5 Windows API.
    """

    def __init__(
        self,
        login: Optional[int | str] = None,
        password: Optional[str] = None,
        server: Optional[str] = None,
        path: Optional[str] = None,
    ):
        raw_login = login or os.getenv("MT5_LOGIN", "477536967")
        try:
            self.login = int(raw_login) if raw_login else None
        except (ValueError, TypeError):
            self.login = None

        self.password = password or os.getenv("MT5_PASSWORD", "")
        self.server = server or os.getenv("MT5_SERVER", "Exness-MT5Trial9")
        self.path = path or os.getenv("MT5_PATH", "")
        self._connected = False
        self._last_failed_at: float = 0.0
        self._last_error_result: Optional[dict[str, Any]] = None

    def connect(self, force: bool = False) -> dict[str, Any]:
        """
        Initializes the connection to the MetaTrader 5 desktop terminal.
        Caches failed IPC attempts for 10 seconds to avoid blocking multi-timeframe
        reads when the desktop terminal is closed or awaiting login.
        """
        if not MT5_AVAILABLE:
            return {
                "success": False,
                "error": "MetaTrader5 Python module not installed in current environment.",
            }

        now = time.monotonic()
        if not force and not self._connected and self._last_error_result and (now - self._last_failed_at) < 30.0:
            return self._last_error_result

        # Initialize MT5 terminal
        init_kwargs = {}
        if self.path and os.path.exists(self.path):
            init_kwargs["path"] = self.path

        if not mt5.initialize(**init_kwargs):
            err_code, err_desc = mt5.last_error()
            logger.warning(f"MT5 initialize failed: {err_code} - {err_desc}")
            self._last_failed_at = now
            self._last_error_result = {
                "success": False,
                "error": f"MetaTrader 5 terminal not found or IPC failed: {err_desc} (Code: {err_code})",
                "hint": "Ensure the Exness MetaTrader 5 desktop app is opened and logged into an active account.",
            }
            return self._last_error_result

        # Check if the MT5 desktop terminal already has an active, connected session
        existing_info = mt5.account_info()
        term_info = mt5.terminal_info()
        already_connected = bool(
            existing_info is not None
            and getattr(existing_info, "login", 0) > 0
            and term_info is not None
            and getattr(term_info, "connected", False)
        )

        # If credentials provided and terminal is either not connected or on a different login, attempt explicit login
        if self.login and self.server and (not already_connected or existing_info.login != self.login):
            login_kwargs = {"login": self.login, "server": self.server}
            if self.password:
                login_kwargs["password"] = self.password

            authorized = mt5.login(**login_kwargs)
            if not authorized:
                err_code, err_desc = mt5.last_error()
                logger.warning(f"MT5 login failed for account {self.login} on {self.server}: {err_code} - {err_desc}")
                # If the desktop terminal was already logged into another valid account, keep using it
                fallback_info = mt5.account_info()
                if not (fallback_info and getattr(fallback_info, "login", 0) > 0 and getattr(mt5.terminal_info(), "connected", False)):
                    self._last_failed_at = now
                    self._last_error_result = {
                        "success": False,
                        "error": f"Login to Exness server '{self.server}' failed: {err_desc} (Code: {err_code})",
                        "login": self.login,
                        "server": self.server,
                    }
                    return self._last_error_result

        account_info = mt5.account_info()
        if account_info is None:
            self._last_failed_at = now
            self._last_error_result = {"success": False, "error": "Failed to retrieve account details from MT5."}
            return self._last_error_result

        self._connected = True
        self._last_error_result = None
        return {
            "success": True,
            "login": account_info.login,
            "server": account_info.server,
            "balance": account_info.balance,
            "equity": account_info.equity,
            "currency": account_info.currency,
            "leverage": account_info.leverage,
            "name": account_info.name,
            "trade_mode": "demo" if "trial" in account_info.server.lower() or "demo" in account_info.server.lower() else "live",
        }

    def is_connected(self) -> bool:
        if not MT5_AVAILABLE:
            return False
        if not self._connected:
            conn = self.connect()
            return bool(conn.get("success"))
        return True

    def get_account_overview(self) -> dict[str, Any]:
        """
        Returns normalized account metrics for TradeFlow AI.
        """
        if not MT5_AVAILABLE:
            return self._simulated_account_overview(error="MetaTrader5 package is unavailable.")

        if not self._connected:
            conn = self.connect()
            if not conn.get("success"):
                return self._simulated_account_overview(error=conn.get("error"))

        info = mt5.account_info()
        if not info:
            return self._simulated_account_overview(error="Could not query MT5 account info.")

        is_cent = "usc" in info.currency.lower() or "cent" in info.currency.lower()
        equity_usd = info.equity / 100.0 if is_cent else info.equity
        balance_usd = info.balance / 100.0 if is_cent else info.balance

        return {
            "broker": "mt5",
            "brokerName": f"Exness MT5 ({info.server})",
            "mode": "demo" if "trial" in info.server.lower() or "demo" in info.server.lower() else "live",
            "accountNumber": str(info.login),
            "currency": info.currency,
            "isCentAccount": is_cent,
            "balance": round(balance_usd, 2),
            "balanceRaw": info.balance,
            "equity": round(equity_usd, 2),
            "equityRaw": info.equity,
            "margin": info.margin,
            "marginFree": info.margin_free,
            "marginLevel": getattr(info, "margin_level", 0.0),
            "leverage": info.leverage,
            "connected": True,
        }

    def get_open_positions(self) -> list[dict[str, Any]]:
        """
        Retrieves all currently active open positions in the MT5 terminal.
        """
        if not MT5_AVAILABLE:
            raise RuntimeError("MetaTrader5 package is unavailable; open positions cannot be verified.")
        if not self._connected:
            connection = self.connect()
            if not connection.get("success"):
                raise RuntimeError(f"MT5 is disconnected; open positions cannot be verified: {connection.get('error', 'connection failed')}")
        positions = mt5.positions_get()
        if positions is None:
            raise RuntimeError("MT5 positions_get returned no data; open positions cannot be verified.")

        result = []
        for pos in positions:
            side = "buy" if pos.type == 0 else "sell"
            entry_px = float(pos.price_open)
            curr_px = float(pos.price_current)
            qty_val = float(pos.volume)
            pnl = round(float(pos.profit), 2)
            cost_val = round(qty_val * entry_px, 2)
            market_val = round(qty_val * curr_px, 2)
            pnl_pct = round((pnl / cost_val) * 100.0, 2) if cost_val > 0 else 0.0

            result.append({
                "id": str(pos.ticket),
                "ticket": pos.ticket,
                "symbol": format_display_symbol(pos.symbol),
                "raw_symbol": pos.symbol,
                "side": side,
                "qty": qty_val,
                "volume": qty_val,
                "avg_entry_price": entry_px,
                "entry_price": entry_px,
                "current_price": curr_px,
                "market_value": market_val,
                "cost_basis": cost_val,
                "unrealized_pnl": pnl,
                "unrealized_pnl_pct": pnl_pct,
                "stop_loss": float(pos.sl) if pos.sl > 0 else None,
                "take_profit": float(pos.tp) if pos.tp > 0 else None,
                "comment": pos.comment,
                "magic": pos.magic,
                "time": pos.time,
            })
        return result

    def _resolve_symbol(self, symbol: str) -> Optional[str]:
        if not MT5_AVAILABLE or not self._connected:
            return None
        clean = symbol.replace("/", "").replace("_", "").replace("-", "").strip().upper()

        alias_map = {
            "BITCOIN": "BTCUSD",
            "ETHEREUM": "ETHUSD",
            "RIPPLE": "XRPUSD",
            "SOLANA": "SOLUSD",
            "DOGECOIN": "DOGEUSD",
            "LITECOIN": "LTCUSD",
            "CARDANO": "ADAUSD",
            "GOLD": "XAUUSD",
            "SILVER": "XAGUSD",
        }
        clean = alias_map.get(clean, clean)

        candidates = [clean, clean + "m", clean + "c", clean + ".m", clean + ".c"]
        # Handle 3-4 letter crypto/metal tickers without quote currency (e.g., BTC -> BTCUSD, ETH -> ETHUSD)
        if len(clean) in (3, 4) and not clean.endswith("USD"):
            for base in [clean + "USD", clean + "USDT"]:
                candidates.extend([base, base + "m", base + "c", base + ".m", base + ".c"])

        for c in candidates:
            info = mt5.symbol_info(c)
            if info is not None:
                if not info.visible:
                    mt5.symbol_select(c, True)
                return c
        return None

    def execute_order(
        self,
        symbol: str,
        side: str,  # "buy" | "sell"
        volume: float = 0.01,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        comment: str = "TradeFlow AI",
    ) -> dict[str, Any]:
        """
        Routes a market execution order directly to Exness via MT5.
        """
        if not MT5_AVAILABLE:
            return {
                "success": False,
                "error": "MetaTrader5 package is not available.",
            }

        if not self._connected:
            conn = self.connect()
            if not conn.get("success"):
                return {
                    "success": False,
                    "error": f"MT5 terminal connection failed: {conn.get('error')}",
                }

        actual_symbol = self._resolve_symbol(symbol)
        if not actual_symbol:
            return {
                "success": False,
                "error": f"Symbol '{symbol}' not found on Exness MT5 terminal.",
            }

        tick = mt5.symbol_info_tick(actual_symbol)
        if not tick:
            return {
                "success": False,
                "error": f"Failed to get price tick for '{actual_symbol}' on Exness MT5.",
            }

        sym_info = mt5.symbol_info(actual_symbol)
        filling_mode = mt5.ORDER_FILLING_IOC
        if sym_info and hasattr(sym_info, "filling_mode"):
            if sym_info.filling_mode & 2:
                filling_mode = mt5.ORDER_FILLING_IOC
            elif sym_info.filling_mode & 1:
                filling_mode = mt5.ORDER_FILLING_FOK
            else:
                filling_mode = mt5.ORDER_FILLING_RETURN

        is_buy = side.lower() == "buy"
        order_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
        price = tick.ask if is_buy else tick.bid

        # Validate broker volume constraints without ever increasing risk.
        try:
            final_volume = normalise_mt5_volume(volume, sym_info)
        except ValueError as exc:
            return {"success": False, "error": f"MT5 order rejected: {exc}"}

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": actual_symbol,
            "volume": float(final_volume),
            "type": order_type,
            "price": float(price),
            "deviation": 20,
            "magic": 100200,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        digits = getattr(sym_info, "digits", 5)
        point = getattr(sym_info, "point", 0.00001)

        if stop_loss is not None:
            sl_val = float(stop_loss)
            if (is_buy and sl_val >= price) or (not is_buy and sl_val <= price):
                return {"success": False, "error": "MT5 order rejected: stop-loss is on the wrong side of the executable market price."}
            request["sl"] = round(sl_val, digits)

        if take_profit is not None:
            tp_val = float(take_profit)
            if (is_buy and tp_val <= price) or (not is_buy and tp_val >= price):
                return {"success": False, "error": "MT5 order rejected: take-profit is on the wrong side of the executable market price."}
            request["tp"] = round(tp_val, digits)

        result = mt5.order_send(request)
        if result is None:
            err_code, err_desc = mt5.last_error()
            return {"success": False, "error": f"MT5 order_send returned None: {err_desc} ({err_code})"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {
                "success": False,
                "error": f"MT5 order rejected: {result.comment} (Retcode: {result.retcode})",
                "retcode": result.retcode,
            }

        return {
            "success": True,
            "ticket": result.order,
            "symbol": actual_symbol,
            "side": side.lower(),
            "volume": final_volume,
            "entry_price": result.price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "message": f"Exness MT5 order #{result.order} executed at {result.price}",
        }

    def close_position(self, ticket: int | str) -> dict[str, Any]:
        """
        Liquidates a position by ticket.
        """
        if not MT5_AVAILABLE:
            return {"success": False, "error": "MetaTrader5 package is not available."}
        if not self._connected:
            conn = self.connect()
            if not conn.get("success"):
                return {"success": False, "error": f"MT5 terminal connection failed: {conn.get('error')}"}

        ticket_int = int(ticket)
        position = None
        for p in mt5.positions_get():
            if p.ticket == ticket_int:
                position = p
                break

        if not position:
            return {"success": False, "error": f"Position ticket {ticket_int} not found."}

        tick = mt5.symbol_info_tick(position.symbol)
        if not tick:
            return {"success": False, "error": f"Cannot get price tick for {position.symbol}."}

        is_buy = position.type == 0
        close_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if is_buy else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": position.ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": close_type,
            "price": close_price,
            "deviation": 20,
            "magic": 100200,
            "comment": "TradeFlow AI Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
            comment = result.comment if result else "No response"
            return {"success": False, "error": f"Close failed: {comment}"}

        # Prefer completed broker history so the journal can include realized
        # P&L and costs when the terminal exposes the deals.
        try:
            history = mt5.history_deals_get(position=position.identifier or position.ticket)
        except Exception:
            history = None
        if history:
            gross_profit = sum(float(getattr(deal, "profit", 0.0) or 0.0) for deal in history)
            costs = sum(
                float(getattr(deal, "commission", 0.0) or 0.0)
                + float(getattr(deal, "swap", 0.0) or 0.0)
                + float(getattr(deal, "fee", 0.0) or 0.0)
                for deal in history
            )
            account_info = mt5.account_info()
            divisor = 100.0 if account_info and ("usc" in account_info.currency.lower() or "cent" in account_info.currency.lower()) else 1.0
            realized_profit = round(gross_profit / divisor, 2)
            fee_paid = round(-costs / divisor, 2)
            pnl_source = "broker_history_net"
        else:
            # Position profit is broker-reported but does not reconcile all
            # round-trip costs, so the benchmark can label it as an estimate.
            account_info = mt5.account_info()
            divisor = 100.0 if account_info and ("usc" in account_info.currency.lower() or "cent" in account_info.currency.lower()) else 1.0
            realized_profit = round(float(position.profit) / divisor, 2)
            fee_paid = None
            pnl_source = "broker_float_at_close"

        return {
            "success": True,
            "ticket": ticket_int,
            "closed_price": result.price,
            "profit": realized_profit,
            "fee_paid": fee_paid,
            "pnl_source": pnl_source,
        }

    def get_closed_position_summary(self, ticket: int | str) -> Optional[dict[str, Any]]:
        """Return realized broker history for a position closed outside TradeFlow."""
        if not MT5_AVAILABLE:
            return None
        if not self._connected and not self.connect().get("success"):
            return None
        position_id = int(ticket)
        try:
            orders = mt5.history_orders_get(ticket=int(ticket))
            if orders:
                position_id = int(getattr(orders[-1], "position_id", 0) or position_id)
            deals = mt5.history_deals_get(position=position_id)
        except Exception:
            return None
        if not deals:
            return None

        out_entries = {
            getattr(mt5, "DEAL_ENTRY_OUT", 1),
            getattr(mt5, "DEAL_ENTRY_OUT_BY", 3),
        }
        closing = [deal for deal in deals if getattr(deal, "entry", None) in out_entries]
        if not closing:
            return None

        gross = sum(float(getattr(deal, "profit", 0.0) or 0.0) for deal in deals)
        costs = sum(
            float(getattr(deal, "commission", 0.0) or 0.0)
            + float(getattr(deal, "swap", 0.0) or 0.0)
            + float(getattr(deal, "fee", 0.0) or 0.0)
            for deal in deals
        )
        account_info = mt5.account_info()
        divisor = 100.0 if account_info and ("usc" in account_info.currency.lower() or "cent" in account_info.currency.lower()) else 1.0
        last_close = max(closing, key=lambda deal: getattr(deal, "time", 0))
        reason_code = getattr(last_close, "reason", None)
        if reason_code == getattr(mt5, "DEAL_REASON_SL", object()):
            exit_reason = "sl"
        elif reason_code == getattr(mt5, "DEAL_REASON_TP", object()):
            exit_reason = "tp"
        else:
            exit_reason = "broker-close"
        close_time = getattr(last_close, "time", None)
        closed_at = datetime.fromtimestamp(close_time, tz=dt_timezone.utc) if close_time else None
        return {
            "closed_price": float(getattr(last_close, "price", 0.0) or 0.0),
            "profit": round(gross / divisor, 2),
            "fee_paid": round(-costs / divisor, 2),
            "pnl_source": "broker_history_net",
            "exit_reason": exit_reason,
            "closed_at": closed_at,
        }

    def update_protection(self, ticket: int | str, stop_loss: float, take_profit: Optional[float] = None) -> dict[str, Any]:
        """
        Updates the broker-side stop-loss and take-profit for an existing position (e.g., Trailing Stop).
        """
        if not MT5_AVAILABLE or not self._connected:
            return {"success": False, "error": "MT5 terminal not connected."}

        ticket_int = int(ticket)
        position = None
        for p in mt5.positions_get():
            if p.ticket == ticket_int:
                position = p
                break

        if not position:
            return {"success": False, "error": f"Position ticket {ticket_int} not found."}

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": position.ticket,
            "symbol": position.symbol,
            "sl": float(stop_loss),
            "tp": float(take_profit) if take_profit else float(position.tp),
        }

        result = mt5.order_send(request)
        if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
            comment = result.comment if result else "No response"
            return {"success": False, "error": f"Protection update failed: {comment}"}

        return {
            "success": True,
            "ticket": ticket_int,
            "new_stop_loss": stop_loss,
            "new_take_profit": take_profit or position.tp,
        }

    def _simulated_account_overview(self, error: Optional[str] = None) -> dict[str, Any]:
        """
        Fallback simulation state while terminal is being launched or configured.
        """
        # Never return invented balances as if they were a real broker account.
        return {
            "broker": "mt5",
            "brokerName": f"Exness MT5 ({self.server})",
            "mode": "disconnected",
            "accountNumber": None,
            "currency": None,
            "isCentAccount": False,
            "balance": 0.0,
            "balanceRaw": 0.0,
            "equity": 0.0,
            "equityRaw": 0.0,
            "margin": 0.0,
            "marginFree": 0.0,
            "leverage": 1,
            "connected": False,
            "statusNote": error or "MT5 account unavailable. Connect a real terminal account before assessing or routing trades.",
        }


# Singleton instance
_mt5_client_instance: Optional[MT5Client] = None


def get_mt5_client() -> MT5Client:
    global _mt5_client_instance
    if _mt5_client_instance is None:
        _mt5_client_instance = MT5Client()
    return _mt5_client_instance
