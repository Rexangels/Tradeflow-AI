from datetime import datetime, timedelta, timezone as dt_timezone
import logging
from typing import Any, Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# Major recurrent High-Impact economic indicators per currency
HIGH_IMPACT_INDICATORS = {
    "USD": ["CPI Inflation Rate", "Non-Farm Payrolls (NFP)", "Fed Interest Rate Decision", "FOMC Statement", "GDP Growth Rate", "PCE Price Index"],
    "EUR": ["ECB Interest Rate Decision", "CPI Inflation Rate", "GDP Growth Rate", "ECB Press Conference"],
    "GBP": ["BoE Interest Rate Decision", "CPI Inflation Rate", "GDP Growth Rate", "Employment Change"],
    "AUD": ["RBA Interest Rate Decision", "CPI Inflation Rate", "Employment Change"],
    "JPY": ["BoJ Interest Rate Decision", "BoJ Monetary Policy Statement", "CPI Inflation Rate"],
    "CAD": ["BoC Interest Rate Decision", "Employment Change", "CPI Inflation Rate"],
}


class EconomicCalendarService:
    """
    Monitors high-impact macroeconomic events and provides automated shields
    against extreme slippage, spread blowouts, and erratic news volatility.
    """

    # Live provider (ForexFactory weekly mirror, no API key) + in-memory cache.
    _CACHE: dict[str, Any] = {"events_raw": [], "fetched_at": None, "source": "uninitialized"}
    _CACHE_TTL_SECONDS = 3600

    @classmethod
    def _calendar_url(cls) -> str:
        try:
            from django.conf import settings as _dj_settings

            return getattr(
                _dj_settings,
                "ECON_CALENDAR_URL",
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            )
        except Exception:
            return "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

    @classmethod
    def _calendar_timeout(cls) -> int:
        try:
            from django.conf import settings as _dj_settings

            return int(getattr(_dj_settings, "ECON_CALENDAR_TIMEOUT_SECONDS", 10))
        except Exception:
            return 10

    @classmethod
    def _fetch_live_raw(cls) -> tuple[list[dict[str, Any]], str]:
        """Fetch raw weekly calendar. Returns (raw_events, source)."""
        import json
        from urllib.request import Request, urlopen

        url = cls._calendar_url()
        # Allow explicit disable for tests / offline: empty URL or 'disabled'.
        if not url or url.strip().lower() in ("disabled", "off", "none"):
            raise ValueError("Economic calendar provider disabled by configuration.")
        req = Request(url, headers={"User-Agent": "TradeFlow-AI/1.0"})
        with urlopen(req, timeout=cls._calendar_timeout()) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        data = json.loads(payload)
        if not isinstance(data, list):
            raise ValueError("Unexpected calendar payload shape.")
        return data, "live_ff_mirror"

    @classmethod
    def _parse_live_event(cls, raw: dict[str, Any], now) -> dict[str, Any] | None:
        try:
            title = str(raw.get("title", "")).strip()
            country = str(raw.get("country", "")).strip().upper()
            date_raw = str(raw.get("date", "")).strip()
            impact_raw = str(raw.get("impact", "")).strip().capitalize()
            if not title or not country or not date_raw:
                return None
            # Map provider impact -> canonical.
            impact_map = {"High": "HIGH", "Medium": "MEDIUM", "Low": "LOW", "Holiday": "HOLIDAY"}
            impact = impact_map.get(impact_raw, "LOW")
            # Parse event time (provider uses -04:00 offsets).
            event_time = datetime.fromisoformat(date_raw)
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=dt_timezone.utc)
            event_utc = event_time.astimezone(dt_timezone.utc)
            minutes_away = round((event_utc - now).total_seconds() / 60.0)
            # Country 'All' applies to every currency (global risk event).
            currency = country if country != "ALL" else "ALL"
            return {
                "id": f"{currency}-{title.replace(' ', '_')[:12]}-{int(event_utc.timestamp())}",
                "currency": currency,
                "name": title,
                "impact": impact,
                "scheduled_time": event_utc.isoformat(),
                "minutes_away": minutes_away,
                "forecast": str(raw.get("forecast", "") or ""),
                "previous": str(raw.get("previous", "") or ""),
                "source": "live_ff_mirror",
            }
        except Exception:
            return None

    @classmethod
    def _fallback_events(cls, now, reason: str = "") -> list[dict[str, Any]]:
        schedule = [
            {"currency": "USD", "name": "CPI Inflation Rate (MoM/YoY)", "impact": "HIGH", "hour_offset": 2.5, "forecast": "3.1%", "previous": "3.2%"},
            {"currency": "EUR", "name": "ECB Monetary Policy Statement", "impact": "HIGH", "hour_offset": 6.0, "forecast": "3.75%", "previous": "4.00%"},
            {"currency": "GBP", "name": "BoE Interest Rate Decision", "impact": "HIGH", "hour_offset": 14.0, "forecast": "5.00%", "previous": "5.25%"},
            {"currency": "AUD", "name": "RBA Rate Statement & Cash Rate", "impact": "HIGH", "hour_offset": 18.5, "forecast": "4.35%", "previous": "4.35%"},
            {"currency": "USD", "name": "Non-Farm Payrolls (NFP)", "impact": "HIGH", "hour_offset": 22.0, "forecast": "175K", "previous": "190K"},
        ]
        events = []
        for s in schedule:
            event_time = now + timedelta(hours=s["hour_offset"])
            events.append({
                "id": f"{s['currency']}-{s['name'].replace(' ', '_')[:10]}-{int(event_time.timestamp())}",
                "currency": s["currency"],
                "name": s["name"],
                "impact": s["impact"],
                "scheduled_time": event_time.isoformat(),
                "minutes_away": round((event_time - now).total_seconds() / 60.0),
                "forecast": s["forecast"],
                "previous": s["previous"],
                "source": "simulated_fallback",
                "fallback_reason": reason,
            })
        if reason:
            logger.warning("Economic calendar using simulated fallback: %s", reason)
        return sorted(events, key=lambda x: x["minutes_away"])

    @classmethod
    def get_calendar_status(cls) -> dict[str, Any]:
        cached = cls._CACHE
        return {
            "source": cached.get("source", "uninitialized"),
            "fetched_at": cached.get("fetched_at").isoformat() if cached.get("fetched_at") else None,
            "raw_event_count": len(cached.get("events_raw", [])),
            "is_live": cached.get("source") == "live_ff_mirror",
            "url": cls._calendar_url(),
        }

    @classmethod
    def get_upcoming_events(cls, hours_ahead: int = 24) -> list[dict[str, Any]]:
        """Live ForexFactory-mirror events with simulated fallback.

        Returns canonical events sorted by minutes_away. Every event carries
        a `source` field: live_ff_mirror | simulated_fallback.
        """
        now = timezone.now().astimezone(dt_timezone.utc)
        # Serve from cache when fresh.
        cached_at = cls._CACHE.get("fetched_at")
        if cached_at and (now - cached_at).total_seconds() < cls._CACHE_TTL_SECONDS and cls._CACHE.get("events_raw"):
            raw = cls._CACHE["events_raw"]
            source = cls._CACHE.get("source", "live_ff_mirror")
            if source == "live_ff_mirror":
                parsed = []
                for r in raw:
                    ev = cls._parse_live_event(r, now)
                    if ev:
                        parsed.append(ev)
                # Filter to window: keep recent past (-120m) through hours_ahead.
                windowed = [e for e in parsed if -120 <= e["minutes_away"] <= hours_ahead * 60]
                return sorted(windowed, key=lambda x: x["minutes_away"])
        # Fetch fresh.
        try:
            raw, source = cls._fetch_live_raw()
            cls._CACHE = {"events_raw": raw, "fetched_at": now, "source": source}
            parsed = []
            for r in raw:
                ev = cls._parse_live_event(r, now)
                if ev:
                    parsed.append(ev)
            windowed = [e for e in parsed if -120 <= e["minutes_away"] <= hours_ahead * 60]
            return sorted(windowed, key=lambda x: x["minutes_away"])
        except Exception as exc:  # Offline / provider down -> explicit fallback.
            cls._CACHE = {"events_raw": [], "fetched_at": now, "source": "simulated_fallback"}
            return cls._fallback_events(now, reason=str(exc))

    @classmethod
    def is_news_blocked(
        cls,
        symbol: str,
        buffer_before_minutes: int = 30,
        buffer_after_minutes: int = 15,
    ) -> tuple[bool, Optional[str], Optional[dict[str, Any]]]:
        """
        Determines if a pair contains a currency that has High-Impact news scheduled
        within the danger window (-30 min to +15 min).
        Returns: (is_blocked, reason_message, event_dict)
        """
        clean = symbol.upper().replace("/", "").replace("_", "").replace("-", "")
        # Extract base and quote currencies for forex (e.g. AUD/USD -> AUD, USD).
        # Crypto (BTC/USD) and US equities are USD-macro sensitive.
        currencies: list[str] = []
        if len(clean) == 6 and clean.isalpha():
            currencies = [clean[:3], clean[3:]]
        elif any(k in clean for k in ("BTC", "ETH", "SOL", "XRP", "DOGE", "XAU", "XAG")):
            # Crypto quoted in USD: USD macro + global risk events matter.
            quote = "USD" if clean.endswith("USD") else clean[-3:]
            currencies = [quote, "USD"]
        elif clean in ("AAPL", "TSLA", "NVDA", "SPY", "MSFT", "AMZN", "GOOGL", "QQQ", "META"):
            currencies = ["USD"]
        else:
            # Unknown format: be conservative and check USD + global events only.
            currencies = ["USD"]

        if not currencies:
            return False, None, None

        events = cls.get_upcoming_events(hours_ahead=12)

        for event in events:
            # Global 'ALL' high-impact events (e.g. IMF meetings flagged HIGH) block everything.
            if event["impact"] == "HIGH" and (event["currency"] in currencies or event["currency"] == "ALL"):
                mins_away = event["minutes_away"]
                # Danger window: between -15 minutes (just happened) and +30 minutes (imminent)
                if -buffer_after_minutes <= mins_away <= buffer_before_minutes:
                    timing_str = f"in {mins_away} minutes" if mins_away > 0 else f"{abs(mins_away)} minutes ago"
                    reason = (
                        f"ECONOMIC NEWS SHIELD ACTIVE: High-impact release '{event['name']}' ({event['currency']}) "
                        f"scheduled {timing_str}. Trading is paused to prevent severe news slippage and spread blowout."
                    )
                    return True, reason, event

        return False, None, None
