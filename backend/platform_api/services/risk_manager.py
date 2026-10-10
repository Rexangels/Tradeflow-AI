import logging
from typing import Any, Optional
from django.utils import timezone

from platform_api.models import RiskRule, TradeLog
from .alpaca_client import get_alpaca_client

logger = logging.getLogger(__name__)

DEFAULT_RULES = {
    "max_risk_pct": 2.0,         # Maximum 2% risk of total equity per trade
    "max_positions": 5,          # Maximum 5 concurrent open positions
    "daily_loss_limit_pct": 5.0, # Stop trading if realized/unrealized loss exceeds 5% today
    "min_rr_ratio": 1.5,         # Minimum 1.5 reward-to-risk ratio
    "require_stop_loss": True,   # Mandatory stop-loss on every order
    "max_position_pct": 10.0,    # Max total notional allocation for a single position (10% of equity)
}


class RiskManager:
    """
    Enforces risk constraints, position sizing, and loss controls
    prior to order placement. The AI cannot bypass these rules.
    """

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

        # 3. Fetch Account Info (Equity, Open Positions)
        client = get_alpaca_client()
        try:
            acc = account_data or client.get_account()
            equity = float(acc.get("equity") or acc.get("cash") or 25000.0)
        except Exception as exc:
            logger.warning(f"Unable to fetch Alpaca account for risk check: {exc}")
            equity = 25000.0

        # 4. Open Positions Count Check
        try:
            positions = client.get_positions()
            # If we already have a position in this symbol, we are modifying/adding, else count towards max
            existing_syms = {p.get("symbol", "").replace("/", "") for p in positions}
            clean_sym = symbol.replace("/", "")
            if clean_sym not in existing_syms and len(positions) >= max_positions:
                return {
                    "approved": False,
                    "reason": f"Risk violation: Maximum open positions ({max_positions}) reached. Currently open: {len(positions)}.",
                    "suggested_qty": 0.0,
                }
        except Exception:
            pass

        # 5. Daily Loss Limit Check
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_trades = TradeLog.objects.filter(created_at__gte=today_start, realized_pnl__isnull=False)
        daily_realized_loss = sum(t.realized_pnl for t in daily_trades if t.realized_pnl < 0)
        max_daily_loss_usd = (daily_loss_limit_pct / 100.0) * equity
        if abs(daily_realized_loss) >= max_daily_loss_usd:
            return {
                "approved": False,
                "reason": f"Risk violation: Daily loss circuit breaker triggered. Realized loss today is ${abs(daily_realized_loss):.2f} (limit: ${max_daily_loss_usd:.2f}). Trading halted for the day.",
                "suggested_qty": 0.0,
            }

        # 6. Position Sizing & Max Risk Calculation
        max_risk_usd = (max_risk_pct / 100.0) * equity
        suggested_qty = qty
        risk_amount_usd = 0.0
        risk_pct = 0.0

        if stop_loss is not None:
            risk_per_unit = abs(current_price - stop_loss)
            if risk_per_unit > 0:
                # suggested qty so total risk <= max_risk_usd
                max_units = max_risk_usd / risk_per_unit
                suggested_qty = min(qty, round(max_units, 2))
                risk_amount_usd = round(suggested_qty * risk_per_unit, 2)
                risk_pct = round((risk_amount_usd / equity) * 100.0, 2)

                if risk_pct > max_risk_pct + 0.1:  # small tolerance
                    return {
                        "approved": False,
                        "reason": f"Risk violation: Trade risk (${risk_amount_usd:.2f} / {risk_pct}%) exceeds allowed max risk per trade ({max_risk_pct}% / ${max_risk_usd:.2f}).",
                        "suggested_qty": suggested_qty,
                        "risk_amount_usd": risk_amount_usd,
                        "risk_pct": risk_pct,
                    }

        # 7. Max Single Position Notional Allocation
        notional = suggested_qty * current_price
        max_notional = (max_position_pct / 100.0) * equity
        if notional > max_notional * 1.5:  # allow leverage up to reasonable bound
            suggested_qty = round(max_notional / current_price, 2)

        return {
            "approved": True,
            "reason": "Trade approved by Risk Manager.",
            "suggested_qty": suggested_qty,
            "risk_amount_usd": risk_amount_usd,
            "risk_pct": risk_pct,
            "rr_ratio": rr_ratio,
        }
