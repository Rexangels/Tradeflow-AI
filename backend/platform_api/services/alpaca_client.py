import json
import logging
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class AlpacaAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class AlpacaClient:
    """
    Robust REST client for Alpaca Trading and Market Data APIs.
    Supports both Paper and Live trading modes.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        mode: Optional[str] = None,
    ):
        self.api_key = api_key or getattr(settings, "ALPACA_API_KEY", "")
        self.api_secret = api_secret or getattr(settings, "ALPACA_API_SECRET", "")
        self.mode = mode or getattr(settings, "ALPACA_MODE", "paper").lower()

        if self.mode == "live":
            self.base_url = getattr(settings, "ALPACA_LIVE_BASE_URL", "https://api.alpaca.markets").rstrip("/")
        else:
            self.base_url = getattr(settings, "ALPACA_PAPER_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")

        self.data_url = getattr(settings, "ALPACA_DATA_URL", "https://data.alpaca.markets").rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Content-Type": "application/json",
            "User-Agent": "TradeFlow-AI/2.0",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
        is_data_api: bool = False,
    ) -> Any:
        base = self.data_url if is_data_api else self.base_url
        clean_path = path if path.startswith("/") else f"/{path}"
        url = f"{base}{clean_path}"

        if params:
            filtered_params = {k: v for k, v in params.items() if v is not None}
            if filtered_params:
                url = f"{url}?{urlencode(filtered_params)}"

        payload_bytes = None
        if data is not None:
            payload_bytes = json.dumps(data).encode("utf-8")

        req = Request(url=url, data=payload_bytes, headers=self._headers(), method=method)

        try:
            with urlopen(req, timeout=20) as response:
                content = response.read().decode("utf-8")
                if not content:
                    return {}
                return json.loads(content)
        except HTTPError as exc:
            body = exc.read().decode("utf-8") if exc.fp else ""
            error_data = None
            try:
                error_data = json.loads(body)
            except Exception:
                pass
            msg = f"Alpaca API HTTP {exc.code} for {method} {url}: {body}"
            logger.error(msg)
            raise AlpacaAPIError(msg, status_code=exc.code, response_data=error_data) from exc
        except (URLError, TimeoutError, OSError) as exc:
            msg = f"Alpaca API network error for {method} {url}: {exc}"
            logger.error(msg)
            raise AlpacaAPIError(msg) from exc

    # ---------------------------------------------------------
    # Account & Portfolio
    # ---------------------------------------------------------
    def get_account(self) -> dict[str, Any]:
        """Fetch account status, balance, equity, and buying power."""
        return self._request("GET", "/v2/account")

    def get_account_configurations(self) -> dict[str, Any]:
        return self._request("GET", "/v2/account/configurations")

    # ---------------------------------------------------------
    # Positions
    # ---------------------------------------------------------
    def get_positions(self) -> list[dict[str, Any]]:
        """List all open positions."""
        return self._request("GET", "/v2/positions") or []

    @staticmethod
    def _format_symbol(symbol: str) -> str:
        """
        Alpaca trading API expects forex symbols WITH a slash: EUR/USD.
        This method ensures correct formatting:
          - 'EURUSD'  -> 'EUR/USD'
          - 'EUR/USD' -> 'EUR/USD'
          - 'BTCUSD'  -> 'BTCUSD'  (crypto stays as-is)
        We detect forex by checking if all 6 chars are alpha letters
        and it's not a known crypto ticker (crypto tickers are usually not
        pure fiat currencies). For now we apply the slash to any 6-char
        alpha symbol that isn't already slashed, assuming forex context.
        """
        # Already has slash — keep as-is
        if "/" in symbol:
            return symbol.upper()
        # Bare 6-char alpha forex symbol like EURUSD -> EUR/USD
        s = symbol.upper().replace("-", "").replace("_", "")
        if len(s) == 6 and s.isalpha():
            return f"{s[:3]}/{s[3:]}"
        return s

    def get_position(self, symbol: str) -> dict[str, Any]:
        """Get open position for a specific symbol."""
        fmt = self._format_symbol(symbol)
        return self._request("GET", f"/v2/positions/{fmt}")

    def close_position(self, symbol: str, qty: Optional[float] = None, percentage: Optional[float] = None) -> dict[str, Any]:
        """Close an open position by symbol."""
        fmt = self._format_symbol(symbol)
        params = {}
        if qty is not None:
            params["qty"] = str(qty)
        if percentage is not None:
            params["percentage"] = str(percentage)
        return self._request("DELETE", f"/v2/positions/{fmt}", params=params)

    def close_all_positions(self, cancel_orders: bool = True) -> list[dict[str, Any]]:
        """Liquidate all open positions."""
        params = {"cancel_orders": str(cancel_orders).lower()}
        return self._request("DELETE", "/v2/positions", params=params)

    # ---------------------------------------------------------
    # Orders
    # ---------------------------------------------------------
    def get_orders(
        self,
        status: str = "open",
        limit: int = 50,
        symbols: Optional[str] = None,
        nested: bool = True,
    ) -> list[dict[str, Any]]:
        """List orders (status: 'open', 'closed', 'all')."""
        params = {
            "status": status,
            "limit": limit,
            "nested": str(nested).lower(),
        }
        if symbols:
            params["symbols"] = symbols
        return self._request("GET", "/v2/orders", params=params) or []

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v2/orders/{order_id}")

    def place_order(
        self,
        symbol: str,
        qty: float,
        side: str,  # "buy" | "sell"
        order_type: str = "market",  # "market" | "limit" | "stop" | "stop_limit"
        time_in_force: str = "gtc",  # "gtc" | "day" | "ioc"
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Place an order with optional bracket (take-profit and stop-loss).
        For forex pairs Alpaca requires the slash format: EUR/USD (not EURUSD).
        """
        fmt_symbol = self._format_symbol(symbol)
        body: dict[str, Any] = {
            "symbol": fmt_symbol,
            "qty": str(qty),
            "side": side.lower(),
            "type": order_type.lower(),
            "time_in_force": time_in_force.lower(),
        }

        if client_order_id:
            body["client_order_id"] = client_order_id
        if limit_price is not None:
            body["limit_price"] = str(round(limit_price, 5))
        if stop_price is not None:
            body["stop_price"] = str(round(stop_price, 5))

        # Bracket order support
        if stop_loss_price is not None or take_profit_price is not None:
            body["order_class"] = "bracket"
            if take_profit_price is not None:
                body["take_profit"] = {"limit_price": str(round(take_profit_price, 5))}
            if stop_loss_price is not None:
                body["stop_loss"] = {"stop_price": str(round(stop_loss_price, 5))}

        return self._request("POST", "/v2/orders", data=body)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v2/orders/{order_id}")

    def cancel_orders_for_symbol(self, symbol: str) -> list[str]:
        """
        Cancel all open orders for a specific symbol.
        Returns list of cancelled order IDs.
        Alpaca's GET /v2/orders supports a `symbols` filter.
        """
        fmt = self._format_symbol(symbol)
        cancelled = []
        try:
            orders = self.get_orders(status="open", symbols=fmt, limit=50, nested=False)
            for order in orders:
                oid = order.get("id") or order.get("order_id")
                if not oid:
                    continue
                try:
                    self._request("DELETE", f"/v2/orders/{oid}")
                    cancelled.append(oid)
                except Exception:
                    pass
        except Exception:
            pass
        return cancelled

    def cancel_all_orders(self) -> list[dict[str, Any]]:
        return self._request("DELETE", "/v2/orders")

    # ---------------------------------------------------------
    # Assets & Supported Pairs
    # ---------------------------------------------------------
    def get_assets(self, asset_class: Optional[str] = None, status: str = "active") -> list[dict[str, Any]]:
        params = {"status": status}
        if asset_class:
            params["asset_class"] = asset_class
        return self._request("GET", "/v2/assets", params=params) or []

    def get_supported_forex_pairs(self) -> list[dict[str, str]]:
        """
        Returns major, minor, and commonly traded forex currency pairs.
        """
        return [
            {"symbol": "EUR/USD", "name": "Euro / US Dollar", "base": "EUR", "quote": "USD"},
            {"symbol": "GBP/USD", "name": "British Pound / US Dollar", "base": "GBP", "quote": "USD"},
            {"symbol": "USD/JPY", "name": "US Dollar / Japanese Yen", "base": "USD", "quote": "JPY"},
            {"symbol": "USD/CHF", "name": "US Dollar / Swiss Franc", "base": "USD", "quote": "CHF"},
            {"symbol": "AUD/USD", "name": "Australian Dollar / US Dollar", "base": "AUD", "quote": "USD"},
            {"symbol": "USD/CAD", "name": "US Dollar / Canadian Dollar", "base": "USD", "quote": "CAD"},
            {"symbol": "NZD/USD", "name": "New Zealand Dollar / US Dollar", "base": "NZD", "quote": "USD"},
            {"symbol": "EUR/GBP", "name": "Euro / British Pound", "base": "EUR", "quote": "GBP"},
            {"symbol": "EUR/JPY", "name": "Euro / Japanese Yen", "base": "EUR", "quote": "JPY"},
            {"symbol": "GBP/JPY", "name": "British Pound / Japanese Yen", "base": "GBP", "quote": "JPY"},
            {"symbol": "AUD/JPY", "name": "Australian Dollar / Japanese Yen", "base": "AUD", "quote": "JPY"},
            {"symbol": "CAD/JPY", "name": "Canadian Dollar / Japanese Yen", "base": "CAD", "quote": "JPY"},
            {"symbol": "EUR/AUD", "name": "Euro / Australian Dollar", "base": "EUR", "quote": "AUD"},
            {"symbol": "EUR/CAD", "name": "Euro / Canadian Dollar", "base": "EUR", "quote": "CAD"},
            {"symbol": "GBP/AUD", "name": "British Pound / Australian Dollar", "base": "GBP", "quote": "AUD"},
            {"symbol": "GBP/CAD", "name": "British Pound / Canadian Dollar", "base": "GBP", "quote": "CAD"},
        ]


# Singleton accessor
_alpaca_client_instance: Optional[AlpacaClient] = None


def get_alpaca_client() -> AlpacaClient:
    global _alpaca_client_instance
    if _alpaca_client_instance is None:
        _alpaca_client_instance = AlpacaClient()
    return _alpaca_client_instance
