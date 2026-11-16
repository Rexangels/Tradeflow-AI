import logging
from typing import Any, Optional
from django.utils import timezone

from platform_api.models import RiskRule, TradeLog
from .alpaca_client import get_alpaca_client

logger = logging.getLogger(__name__)

DEFAULT_RULES = {
    "max_risk_pct": 1.0,                   # Conservative default: maximum 1% risk per trade
    "max_positions": 1,                    # Conservative default: one open position
    "max_usd_directional_positions": 2,    # Maximum 2 correlated same-direction USD positions
    "daily_loss_limit_pct": 2.0,           # Stop trading at 2% combined realized/unrealized daily loss
    "min_rr_ratio": 1.5,                   # Minimum 1.5 reward-to-risk ratio
    "require_stop_loss": True,             # Mandatory stop-loss on every order
    "max_position_pct": 10.0,              # Max single-position notional allocation on unleveraged accounts
}


class RiskManager:
    """
    Enforces risk constraints, position sizing, currency correlation limits,
    and loss controls prior to order placement. The AI cannot bypass these rules.
    """

    @staticmethod
    def get_usd_direction(symbol: str, side: str) -> Optional[str]:
        """
        Determines whether a trade is net LONG_USD or SHORT_USD so the portfolio
        cannot accidentally stack 5 identical USD directional bets across pairs.
        """
        clean = symbol.replace("/", "").replace("_", "").replace("-", "").upper()
        for suffix in ("M", "C"):
            if len(clean) > 6 and clean.endswith(suffix):
                clean = clean[:-1]
        is_buy = side.lower() in ("buy", "long")
        if len(clean) == 6 and clean.startswith("USD"):
            return "LONG_USD" if is_buy else "SHORT_USD"
        if clean.endswith("USD") or clean.endswith("USDT"):
            return "SHORT_USD" if is_buy else "LONG_USD"
        return None

    @staticmethod
    def unit_risk_in_usd(symbol: str, current_price: float, stop_loss: float) -> float:
        """
        Converts price distance |current_price - stop_loss| into USD risk per 1 base unit.
        - For XXX/USD pairs (EUR/USD, GBP/USD, BTC/USD, XAU/USD): 1 unit risk is already in USD.
        - For USD/XXX pairs (USD/JPY, USD/CAD, USD/CHF): 1 unit risk in quote currency
          is divided by current_price to convert to USD.
        - For cross pairs ending in JPY (EUR/JPY, GBP/JPY): approximate JPY->USD using 150.0
          or current_price if ~100-200.
        """
        raw_dist = abs(current_price - stop_loss)
        if raw_dist <= 0 or current_price <= 0:
            return 0.0
        clean = symbol.replace("/", "").replace("_", "").replace("-", "").upper()
        if len(clean) >= 6 and clean[:3] == "USD" and not clean.endswith("USD"):
            return raw_dist / current_price
        if "JPY" in clean and not clean.startswith("USD"):
            # Cross JPY pair (e.g., EURJPY, GBPJPY): convert JPY distance to approximate USD
            usd_jpy_approx = 152.0
            return raw_dist / usd_jpy_approx
        return raw_dist

    @classmethod
    def get_rule_value(cls, key: str, default: Any = None) -> Any:
        rule = RiskRule.objects.filter(key=key).first()
        if not rule or not rule.value:
            return DEFAULT_RULES.get(key, default)
        if isinstance(rule.value, dict) and "value" in rule.value:
            return rule.value["value"]
        return rule.value

    @classmethod
    def get_all_rules(cls) -> dict[str, Any]:
        rules = dict(DEFAULT_RULES)
        for r in RiskRule.objects.all():
            val = r.value.get("value") if isinstance(r.value, dict) and "value" in r.value else r.value
            rules[r.key] = val

        # Existing database rules may outlive code defaults. In micro mode,
        # treat these values as hard ceilings/floors so stale DB settings cannot
        # silently relax the $10 account's safety profile.
        from django.conf import settings
        if getattr(settings, "TRADEFLOW_MICRO_ACCOUNT_MODE", False):
            rules["max_risk_pct"] = min(float(rules.get("max_risk_pct", 1.0)), 1.0)
            rules["max_positions"] = min(int(rules.get("max_positions", 1)), 1)
            rules["daily_loss_limit_pct"] = min(float(rules.get("daily_loss_limit_pct", 2.0)), 2.0)
            rules["max_position_pct"] = min(float(rules.get("max_position_pct", 10.0)), 10.0)
            rules["min_rr_ratio"] = max(float(rules.get("min_rr_ratio", 1.5)), 1.5)
            rules["require_stop_loss"] = True
        return rules

    @classmethod
    def update_rule(cls, key: str, value: Any) -> RiskRule:
        rule, _ = RiskRule.objects.get_or_create(key=key)
        rule.value = {"value": value}
        rule.save()
        return rule

    @classmethod
    def assess_order(
        cls,
        symbol: str,
        side: str,  # "buy" | "sell"
        qty: float,
        current_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        account_data: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Evaluates a proposed trade against all active risk rules.
        Returns:
            {
                "approved": bool,
                "reason": str,
                "suggested_qty": float,
                "risk_amount_usd": float,
                "risk_pct": float,
                "rr_ratio": float,
            }
        """
        rules = cls.get_all_rules()
        require_sl = rules.get("require_stop_loss", True)
        max_risk_pct = float(rules.get("max_risk_pct", 2.0))
        max_positions = int(rules.get("max_positions", 5))
        min_rr_ratio = float(rules.get("min_rr_ratio", 1.5))
        daily_loss_limit_pct = float(rules.get("daily_loss_limit_pct", 5.0))
        max_position_pct = float(rules.get("max_position_pct", 10.0))

        # 0A. Economic News Shield (Blocks trades 30m before / 15m after Red-Folder releases)
        from .economic_calendar import EconomicCalendarService
        is_news_blocked, news_reason, news_event = EconomicCalendarService.is_news_blocked(symbol)
        if is_news_blocked:
            return {
                "approved": False,
                "reason": news_reason,
                "news_shield_active": True,
                "news_event": news_event,
                "suggested_qty": 0.0,
            }

        # 0B. Session Rollover Guardrail (21:00 - 23:00 UTC wide spreads)
        from .session_filter import SessionFilterService
        session_info = SessionFilterService.get_current_session_info()
        if session_info.get("is_rollover"):
            return {
                "approved": False,
                "reason": f"Session Guardrail: Bank Rollover / Off-Hours ({session_info['current_utc_time']}). Interbank spreads widen significantly; new orders paused.",
                "suggested_qty": 0.0,
            }

        # 1. Stop-Loss Validation
        if require_sl and not stop_loss:
            return {
                "approved": False,
                "reason": "Risk violation: Stop-loss is strictly required for all trades.",
                "suggested_qty": 0.0,
            }

        if stop_loss is not None:
            if side.lower() == "buy" and stop_loss >= current_price:
                return {
                    "approved": False,
                    "reason": f"Risk violation: Stop-loss ({stop_loss}) must be below current price ({current_price}) for a BUY order.",
                    "suggested_qty": 0.0,
                }
            if side.lower() == "sell" and stop_loss <= current_price:
                return {
                    "approved": False,
                    "reason": f"Risk violation: Stop-loss ({stop_loss}) must be above current price ({current_price}) for a SELL order.",
                    "suggested_qty": 0.0,
                }

        if take_profit is not None:
            if side.lower() == "buy" and take_profit <= current_price:
                return {"approved": False, "reason": "Risk violation: take-profit must be above current price for a BUY order.", "suggested_qty": 0.0}
            if side.lower() == "sell" and take_profit >= current_price:
                return {"approved": False, "reason": "Risk violation: take-profit must be below current price for a SELL order.", "suggested_qty": 0.0}

        # 2. Reward-to-Risk Ratio Validation
        rr_ratio = 0.0
        if stop_loss is not None and take_profit is not None:
            risk_dist = abs(current_price - stop_loss)
            reward_dist = abs(take_profit - current_price)
            if risk_dist > 0:
                rr_ratio = round(reward_dist / risk_dist, 2)
                if rr_ratio < min_rr_ratio:
                    return {
                        "approved": False,
                        "reason": f"Risk violation: Reward-to-Risk ratio ({rr_ratio}R) is below the minimum required ({min_rr_ratio}R).",
                        "suggested_qty": 0.0,
                        "rr_ratio": rr_ratio,
                    }

        # 3. Fetch Account Info (Equity, Leverage, Active Broker)
        from .order_execution import OrderExecutionService
        try:
            acc = account_data or OrderExecutionService.get_account_overview()
            if acc.get("connected") is False:
                return {"approved": False, "reason": "Risk violation: broker account is disconnected; live equity cannot be verified.", "suggested_qty": 0.0}
            equity_value = acc.get("equity")
            if equity_value is None:
                equity_value = acc.get("cash")
            if equity_value is None or float(equity_value) <= 0:
                return {"approved": False, "reason": "Risk violation: valid positive broker equity is unavailable.", "suggested_qty": 0.0}
            equity = float(equity_value)
            leverage = float(acc.get("leverage") or 1.0)
            is_mt5 = acc.get("broker") == "mt5" or acc.get("active_broker") == "mt5"
            is_cent = bool(acc.get("isCentAccount", False))
        except Exception as exc:
            logger.error("Unable to verify broker account equity; rejecting order: %s", exc)
            return {"approved": False, "reason": "Risk violation: broker account information could not be verified. Order rejected.", "suggested_qty": 0.0}

        # 4. Open Positions Count & Correlated USD Exposure Check
        max_usd_dir = int(rules.get("max_usd_directional_positions", 2))
        try:
            positions = OrderExecutionService.get_open_positions()
            existing_syms = {p.get("symbol", "").replace("/", "") for p in positions}
            clean_sym = symbol.replace("/", "")
            if clean_sym not in existing_syms and len(positions) >= max_positions:
                return {
                    "approved": False,
                    "reason": f"Risk violation: Maximum open positions ({max_positions}) reached. Currently open: {len(positions)}.",
                    "suggested_qty": 0.0,
                }
            # Check correlated USD directional concentration
            proposed_usd_dir = cls.get_usd_direction(symbol, side)
            if proposed_usd_dir and clean_sym not in existing_syms:
                same_dir_positions = [
                    p.get("symbol", "")
                    for p in positions
                    if cls.get_usd_direction(p.get("symbol", ""), p.get("side", "buy")) == proposed_usd_dir
                ]
                if len(same_dir_positions) >= max_usd_dir:
                    return {
                        "approved": False,
                        "reason": (
                            f"Risk violation: Correlated USD exposure limit ({max_usd_dir} {proposed_usd_dir} positions) "
                            f"reached ({', '.join(same_dir_positions)}). Avoid stacking identical USD macro bets."
                        ),
                        "suggested_qty": 0.0,
                    }
        except Exception as exc:
            logger.error("Unable to verify open broker positions; rejecting order: %s", exc)
            return {"approved": False, "reason": "Risk violation: open positions could not be verified. Order rejected.", "suggested_qty": 0.0}

        # 5. Daily loss circuit breaker: realized losses today plus current
        # negative unrealized P&L. Unknown position data fails closed above.
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_trades = TradeLog.objects.filter(created_at__gte=today_start, realized_pnl__isnull=False)
        daily_realized_loss = sum(t.realized_pnl for t in daily_trades if t.realized_pnl < 0)
        unrealized_loss = sum(min(0.0, float(p.get("unrealized_pnl") or 0.0)) for p in positions)
        combined_daily_loss = abs(daily_realized_loss) + abs(unrealized_loss)
        max_daily_loss_usd = (daily_loss_limit_pct / 100.0) * equity
        if combined_daily_loss >= max_daily_loss_usd:
            return {
                "approved": False,
                "reason": f"Risk violation: daily loss circuit breaker triggered. Combined realized and unrealized losses are ${combined_daily_loss:.2f} (limit: ${max_daily_loss_usd:.2f}). Trading halted.",
                "suggested_qty": 0.0,
            }

        # 6. Position Sizing & Max Risk Calculation (Unit vs Lot & Quote-Currency Aware)
        max_risk_usd = (max_risk_pct / 100.0) * equity
        suggested_qty = qty
        risk_amount_usd = 0.0
        risk_pct = 0.0

        clean_norm = symbol.replace("/", "").replace("_", "").replace("-", "").upper()
        is_crypto = any(c in clean_norm for c in ("BTC", "ETH", "SOL", "XRP", "DOGE", "LTC", "ADA", "BNB")) or current_price > 500
        # Detect whether caller passed MT5 FX lots (e.g. 0.01 lot) vs base units (e.g. 1000 units)
        qty_is_lots = is_mt5 and not is_crypto and 0 < qty <= 10.0
        lot_unit_multiplier = 1000.0 if is_cent else 100000.0
        effective_units = (qty * lot_unit_multiplier) if qty_is_lots else qty

        if stop_loss is not None:
            risk_per_unit = cls.unit_risk_in_usd(symbol, current_price, stop_loss)
            if risk_per_unit > 0:
                max_units = max_risk_usd / risk_per_unit
                if qty_is_lots:
                    # Round DOWN to the broker's 0.01-lot step. Never force a
                    # minimum lot that would exceed the calculated risk budget.
                    import math
                    max_lots = math.floor((max_units / lot_unit_multiplier) * 100.0) / 100.0
                    if max_lots < 0.01:
                        return {"approved": False, "reason": "Risk violation: calculated risk budget is below the broker's 0.01-lot minimum; trade rejected.", "suggested_qty": 0.0, "risk_amount_usd": 0.0, "risk_pct": 0.0}
                    suggested_qty = min(qty, max_lots)
                    effective_units = suggested_qty * lot_unit_multiplier
                else:
                    suggested_qty = min(qty, max_units)
                    effective_units = suggested_qty

                risk_amount_usd = round(effective_units * risk_per_unit, 2)
                risk_pct = round((risk_amount_usd / equity) * 100.0, 2)

                if risk_pct > max_risk_pct + 0.1:  # small tolerance
                    return {
                        "approved": False,
                        "reason": f"Risk violation: Trade risk (${risk_amount_usd:.2f} / {risk_pct}%) exceeds allowed max risk per trade ({max_risk_pct}% / ${max_risk_usd:.2f}).",
                        "suggested_qty": suggested_qty,
                        "risk_amount_usd": risk_amount_usd,
                        "risk_pct": risk_pct,
                    }

        # 7. Max Single Position Notional Allocation (Applies to unleveraged accounts or when no SL is set)
        if stop_loss is None or leverage <= 5.0:
            notional = effective_units * current_price
            max_notional = (max_position_pct / 100.0) * equity * max(1.0, leverage)
            if notional > max_notional and current_price > 0:
                capped_units = max_notional / current_price
                if qty_is_lots:
                    import math
                    suggested_qty = math.floor((capped_units / lot_unit_multiplier) * 100.0) / 100.0
                    if suggested_qty < 0.01:
                        return {"approved": False, "reason": "Risk violation: broker minimum lot exceeds the permitted position allocation.", "suggested_qty": 0.0}
                else:
                    suggested_qty = min(suggested_qty, capped_units)

        return {
            "approved": True,
            "reason": "Trade approved by Risk Manager.",
            "suggested_qty": suggested_qty,
            "risk_amount_usd": risk_amount_usd,
            "risk_pct": risk_pct,
            "rr_ratio": rr_ratio,
        }
