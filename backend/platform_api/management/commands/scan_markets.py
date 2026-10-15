"""Scheduled M15-close market scan. Alerts only on False -> True flips.

Usage (every 15 min at :01, :16, :31, :46):
    python backend/manage.py scan_markets
    python backend/manage.py scan_markets --symbols EUR/USD,GBP/USD --auto-trade

State lives in AppSetting(scan_state) so restarts don't re-spam.
Respects news shield + session gates before writing AISignal.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from platform_api.models import Agent, AISignal, AppSetting


class Command(BaseCommand):
    help = "Scan watched markets and record AISignal flips for the frontend feed."

    def add_arguments(self, parser):
        parser.add_argument("--symbols", default="", help="Comma-separated symbols (default: watched + universe).")
        parser.add_argument("--auto-trade", action="store_true", help="Execute TRADEABLE flips (default: alert only).")

    def handle(self, *args, **options):
        from platform_api.services.alignment_scanner import DEFAULT_SCAN_UNIVERSE
        from platform_api.services.economic_calendar import EconomicCalendarService
        from platform_api.services.multi_timeframe import MultiTimeframeService
        from platform_api.services.order_execution import OrderExecutionService
        from platform_api.services.session_filter import SessionFilterService

        raw = (options.get("symbols") or "").strip()
        if raw:
            universe = [s.strip() for s in raw.split(",") if s.strip()]
        else:
            from platform_api.models import ForexPairConfig

            watched = list(
                ForexPairConfig.objects.filter(is_watched=True).values_list("symbol", flat=True)
            )
            universe = watched or DEFAULT_SCAN_UNIVERSE
            # Chat-created tracking watches always join the scan, even if unwatched.
            try:
                watch_raw = AppSetting.objects.filter(key="tracking_watches").first()
                if watch_raw and isinstance(watch_raw.value, dict):
                    for sym in watch_raw.value.keys():
                        if sym not in universe:
                            universe.append(sym)
            except Exception:
                pass

        try:
            state_raw = AppSetting.objects.filter(key="scan_state").first()
            state = json.loads(json.dumps(state_raw.value)) if state_raw else {}
        except Exception:
            state = {}

        session = SessionFilterService.get_current_session_info()
        agent = Agent.objects.order_by("-updated_at").first()
        if agent is None:
            from django.contrib.auth.models import User

            user = User.objects.order_by("id").first()
            if user is None:
                user = User.objects.create_user(username="scan_bot", email="scan@tradeflow.local")
            agent = Agent.objects.create(
                owner=user, name="Scan Bot", type="custom", reward_style="balanced",
                risk_tolerance=0.4, holding_behavior="swing", strategies=[],
            )
        flips: list[str] = []

        for sym in universe:
            try:
                mtf = MultiTimeframeService.analyze_top_down(sym)
            except Exception as exc:
                self.stdout.write(f"{sym}: scan failed ({exc})")
                continue
            blocked, reason, _ = EconomicCalendarService.is_news_blocked(sym)
            aligned = bool(mtf["is_aligned"]) and not blocked and session.get("favorable_for_trading", True)
            prev = bool(state.get(sym, {}).get("aligned", False))
            state[sym] = {
                "aligned": aligned,
                "quality": mtf["confluence_quality"],
                "side": mtf["suggested_side"],
                "checked_at": timezone.now().isoformat(),
            }
            if aligned and not prev:
                direction = "long" if mtf["suggested_side"] == "buy" else "short"
                sig = AISignal.objects.create(
                    agent=agent,
                    symbol=sym,
                    timeframe="4h+1h+15m",
                    direction=direction,
                    confidence=float(mtf["composite_score"]) / 100.0,
                    reasoning=(
                        f"SCAN FLIP {sym}: {mtf['macro_bias_4h']} {mtf['confluence_quality']} "
                        f"{mtf['composite_score']}/100 side={mtf['suggested_side']} "
                        f"entry={mtf['entry_price']} SL={mtf['stop_loss']} TP={mtf['take_profit']} "
                        f"session={session['primary_session']} news=CLEAR"
                    ),
                    indicators={
                        "macro_bias_4h": mtf["macro_bias_4h"],
                        "confluence_quality": mtf["confluence_quality"],
                        "composite_score": mtf["composite_score"],
                        "entry_price": mtf["entry_price"],
                        "stop_loss": mtf["stop_loss"],
                        "take_profit": mtf["take_profit"],
                        "source": "scan_markets",
                    },
                    acted_on=False,
                )
                flips.append(f"{sym} {direction} ({mtf['composite_score']}) id={sig.id}")
                if options.get("auto_trade") and mtf["composite_score"] >= 65:
                    OrderExecutionService.execute_order(
                        symbol=sym,
                        side=mtf["suggested_side"],
                        qty=1000.0,
                        stop_loss=mtf["stop_loss"],
                        take_profit=mtf["take_profit"],
                        agent=agent,
                        ai_reasoning=f"scan_markets auto-trade flip {mtf['confluence_quality']}",
                        signal_id=str(sig.id),
                    )
            elif blocked and mtf["is_aligned"]:
                self.stdout.write(f"{sym}: aligned but news-blocked ({reason})")

        AppSetting.objects.update_or_create(key="scan_state", defaults={"value": state})
        if flips:
            self.stdout.write(self.style.SUCCESS(f"Flips: {'; '.join(flips)}"))
        else:
            self.stdout.write("No flips (all WAITING/RANGING/CONFLICTED or already alerted).")
