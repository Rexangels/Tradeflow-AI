from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import AppSetting, PaperAccount, PaperOrder, PaperPosition, PaperSession, UsageEvent
from ..presenters import serialize_paper_order, serialize_position
from .market_data import latest_price


FEE_RATE = 0.001
SLIPPAGE_RATE = 0.0005
DEFAULT_RISK_POLICY = {
    "tradingEnabled": True,
    "maxOrderNotional": 2500,
    "maxOpenPositions": 3,
    "maxDailyLoss": 500,
}


def get_or_create_account(user):
    account, _ = PaperAccount.objects.get_or_create(
        owner=user,
        defaults={"cash_balance": 10000, "equity": 10000, "realized_pnl": 0},
    )
    return account


def account_snapshot(user):
    account = get_or_create_account(user)
    positions_payload = []
    equity = account.cash_balance
    risk_policy = get_risk_policy()
    current_open_positions = account.positions.filter(quantity__gt=0).count()

    for position in account.positions.all().order_by("symbol"):
        market_price = latest_price(position.symbol)
        position_payload = serialize_position(position, market_price)
        positions_payload.append(position_payload)
        equity += position_payload["marketValue"]

    account.equity = round(equity, 4)
    account.save(update_fields=["equity", "updated_at"])

    recent_orders = [serialize_paper_order(order) for order in account.orders.order_by("-created_at")[:10]]
    return {
        "id": str(account.id),
        "cashBalance": round(account.cash_balance, 4),
        "equity": round(account.equity, 4),
        "realizedPnl": round(account.realized_pnl, 4),
        "updatedAt": account.updated_at.isoformat(),
        "positions": positions_payload,
        "recentOrders": recent_orders,
        "riskPolicy": {
            **risk_policy,
            "currentOpenPositions": current_open_positions,
            "dailyRealizedLoss": round(_daily_realized_loss(account), 4),
        },
    }


@transaction.atomic
def place_order(user, payload: dict):
    account = get_or_create_account(user)
    session = _resolve_session(user, account, payload.get("sessionId"))
    risk_policy = get_risk_policy()
    symbol = payload["symbol"].upper()
    market_price = latest_price(symbol, payload.get("timeframe", "1h"))
    position = PaperPosition.objects.select_for_update().filter(paper_account=account, symbol=symbol).first()

    _enforce_risk_policy(account, payload, risk_policy, position, market_price)
    realized_pnl = 0.0

    if payload["side"] == "buy":
        fill_price = market_price * (1 + SLIPPAGE_RATE)
        quantity = payload.get("quantity") or (payload["notional"] / fill_price)
        notional = quantity * fill_price
        fee_paid = notional * FEE_RATE

        if account.cash_balance < notional + fee_paid:
            raise ValueError("Insufficient paper cash balance for this order.")

        account.cash_balance -= notional + fee_paid
        if position:
            total_quantity = position.quantity + quantity
            position.average_entry_price = (
                (position.quantity * position.average_entry_price) + (quantity * fill_price)
            ) / total_quantity
            position.quantity = total_quantity
            position.save(update_fields=["average_entry_price", "quantity", "updated_at"])
        else:
            position = PaperPosition.objects.create(
                owner=user,
                paper_account=account,
                symbol=symbol,
                quantity=quantity,
                average_entry_price=fill_price,
            )

    else:
        if not position or position.quantity <= 0:
            raise ValueError(f"No open paper position exists for {symbol}.")

        fill_price = market_price * (1 - SLIPPAGE_RATE)
        quantity = payload.get("quantity") or (payload["notional"] / fill_price)
        if quantity > position.quantity:
            raise ValueError("Sell quantity exceeds the current paper position.")

        notional = quantity * fill_price
        fee_paid = notional * FEE_RATE
        realized = notional - fee_paid - (quantity * position.average_entry_price)
        realized_pnl = realized

        account.cash_balance += notional - fee_paid
        account.realized_pnl += realized
        remaining = position.quantity - quantity
        if remaining <= 0:
            position.delete()
        else:
            position.quantity = remaining
            position.save(update_fields=["quantity", "updated_at"])

    account.save(update_fields=["cash_balance", "realized_pnl", "updated_at"])
    order = PaperOrder.objects.create(
        owner=user,
        paper_account=account,
        session=session,
        symbol=symbol,
        side=payload["side"],
        quantity=quantity,
        fill_price=round(fill_price, 4),
        notional=round(notional, 4),
        fee_paid=round(fee_paid, 4),
        realized_pnl=round(realized_pnl, 4),
        status="filled",
    )

    UsageEvent.objects.create(
        owner=user,
        category="paper_order",
        reference_id=str(order.id),
        quantity=1,
        metadata={"symbol": symbol, "side": payload["side"]},
    )

    return {
        "sessionId": str(session.id),
        "order": serialize_paper_order(order),
        "account": account_snapshot(user),
    }


def session_snapshot(user, session_id):
    session = PaperSession.objects.get(id=session_id, owner=user)
    account_payload = account_snapshot(user)
    return {
        "id": str(session.id),
        "createdAt": session.created_at.isoformat(),
        "orders": [serialize_paper_order(order) for order in session.orders.order_by("created_at")],
        "positions": account_payload["positions"],
        "cashBalance": account_payload["cashBalance"],
        "equity": account_payload["equity"],
    }


def _resolve_session(user, account, session_id):
    if session_id:
        return PaperSession.objects.get(id=session_id, owner=user, paper_account=account)
    active = PaperSession.objects.filter(owner=user, paper_account=account, closed_at__isnull=True).order_by("-created_at").first()
    if active:
        return active
    return PaperSession.objects.create(owner=user, paper_account=account)


def get_risk_policy() -> dict:
    stored = AppSetting.objects.filter(key="paper_risk_policy").values_list("value", flat=True).first()
    policy = dict(DEFAULT_RISK_POLICY)
    if isinstance(stored, dict):
        policy.update(stored)
    return policy


def system_status() -> dict:
    return {
        "databaseEngine": settings.DATABASES["default"]["ENGINE"],
        "sqliteMode": settings.DATABASES["default"]["ENGINE"].endswith("sqlite3"),
        "geminiConfigured": bool(settings.GEMINI_API_KEY),
        "marketDataProviderUrl": settings.BINANCE_API_BASE_URL,
        "marketDataFallbackMode": settings.MARKET_DATA_FALLBACK_MODE,
        "paperTradingEnabled": get_risk_policy()["tradingEnabled"],
        "liveTradingEnabled": False,
    }


def _enforce_risk_policy(account, payload: dict, risk_policy: dict, position, market_price: float):
    if not risk_policy["tradingEnabled"]:
        raise ValueError("Paper trading is currently disabled by the global kill switch.")

    projected_notional = payload.get("notional")
    if projected_notional is None and payload.get("quantity"):
        projected_notional = payload["quantity"] * market_price
    projected_notional = float(projected_notional or 0)

    if payload["side"] == "buy" and projected_notional > risk_policy["maxOrderNotional"]:
        raise ValueError(
            f"Order rejected by risk policy: max order notional is ${risk_policy['maxOrderNotional']:.2f}."
        )

    if payload["side"] == "buy":
        current_open_positions = account.positions.filter(quantity__gt=0).count()
        opening_new_symbol = position is None or position.quantity <= 0
        if opening_new_symbol and current_open_positions >= risk_policy["maxOpenPositions"]:
            raise ValueError(
                f"Order rejected by risk policy: max open positions is {risk_policy['maxOpenPositions']}."
            )

    daily_loss = _daily_realized_loss(account)
    if daily_loss >= risk_policy["maxDailyLoss"]:
        raise ValueError(
            f"Order rejected by risk policy: daily realized loss limit of ${risk_policy['maxDailyLoss']:.2f} reached."
        )


def _daily_realized_loss(account) -> float:
    day_start = timezone.now() - timedelta(hours=24)
    realized = account.orders.filter(created_at__gte=day_start, side="sell").values_list("realized_pnl", flat=True)
    total = sum(value for value in realized if value < 0)
    return abs(total)
