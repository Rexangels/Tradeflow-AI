from datetime import datetime, timezone as dt_timezone
import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


class SessionFilterService:
    """
    Evaluates global FX trading session windows and institutional liquidity conditions.
    Restricts or warns when trading in low-liquidity rollover or chop sessions.
    """

    @classmethod
    def get_current_session_info(cls) -> dict[str, Any]:
        """
        Determines active global market sessions in UTC.
        """
        now = timezone.now().astimezone(dt_timezone.utc)
        weekday = now.weekday()  # 0=Monday, 5=Saturday, 6=Sunday
        hour = now.hour + (now.minute / 60.0)

        # Check weekend: Friday 21:00 UTC through Sunday 21:00 UTC
        is_weekend = (weekday == 4 and hour >= 21.0) or (weekday == 5) or (weekday == 6 and hour < 21.0)
        if is_weekend:
            return {
                "current_utc_time": now.strftime("%H:%M:%S UTC"),
                "current_hour_utc": round(hour, 2),
                "primary_session": "Weekend Crypto Window (Forex Closed)",
                "active_sessions": ["24/7 Crypto Markets"],
                "liquidity_rating": "MODERATE (24/7 Crypto Active | Forex Closed)",
                "liquidity_score": 60,
                "favorable_for_trading": True,
                "advice": "Traditional interbank Forex & equity markets are closed for the weekend. 24/7 Cryptocurrency markets (BTC, ETH) on MetaTrader 5 (Exness) are active.",
                "is_london_ny_overlap": False,
                "is_rollover": False,
                "is_weekend": True,
            }

        # Active market flags
        is_london = 7.0 <= hour < 16.0
        is_new_york = 12.0 <= hour < 21.0
        is_tokyo = 0.0 <= hour < 9.0
        is_sydney = (21.0 <= hour <= 24.0) or (0.0 <= hour < 6.0)
        is_rollover = 21.0 <= hour < 23.0  # Daily bank rollover (widest spreads)

        # Overlap determination
        is_london_ny_overlap = is_london and is_new_york  # 12:00 - 16:00 UTC: Peak Global Liquidity

        if is_london_ny_overlap:
            session_name = "London / New York Overlap"
            liquidity_rating = "OPTIMAL"
            liquidity_score = 95
            favorable_for_trading = True
            advice = "Peak global volume. Spreads are at their tightest. Optimal window for breakout and momentum strategies."
        elif is_london:
            session_name = "London European Session"
            liquidity_rating = "HIGH"
            liquidity_score = 85
            favorable_for_trading = True
            advice = "High European volume and strong directional trends. Excellent liquidity for EUR and GBP pairs."
        elif is_new_york:
            session_name = "New York Session"
            liquidity_rating = "HIGH"
            liquidity_score = 80
            favorable_for_trading = True
            advice = "US afternoon session. Good liquidity, watch for mid-day pullbacks."
        elif is_tokyo:
            session_name = "Asian / Tokyo Session"
            liquidity_rating = "MODERATE"
            liquidity_score = 50
            favorable_for_trading = True  # Good for JPY, AUD, NZD
            advice = "Asian session range-bound environment. Best for mean-reversion and JPY/AUD pairs. Reduced volume."
        elif is_rollover:
            session_name = "Bank Rollover / Off-Hours"
            liquidity_rating = "HAZARDOUS"
            liquidity_score = 15
            favorable_for_trading = False
            advice = "Daily interbank rollover. Spreads widen dramatically. Algorithms should pause new order entries."
        else:
            session_name = "Sydney Session"
            liquidity_rating = "LOW"
            liquidity_score = 40
            favorable_for_trading = False
            advice = "Low interbank liquidity. Spreads slightly elevated."

        active_sessions = []
        if is_london:
            active_sessions.append("London")
        if is_new_york:
            active_sessions.append("New York")
        if is_tokyo:
            active_sessions.append("Tokyo")
        if is_sydney:
            active_sessions.append("Sydney")

        return {
            "current_utc_time": now.strftime("%H:%M:%S UTC"),
            "current_hour_utc": round(hour, 2),
            "primary_session": session_name,
            "active_sessions": active_sessions,
            "liquidity_rating": liquidity_rating,
            "liquidity_score": liquidity_score,
            "favorable_for_trading": favorable_for_trading,
            "advice": advice,
            "is_london_ny_overlap": is_london_ny_overlap,
            "is_rollover": is_rollover,
        }
