"""Persistent, content-addressed market-data snapshots for reproducible research."""
from datetime import datetime, timezone as dt_timezone
import hashlib
import json

from django.db import transaction
from django.utils import timezone

from platform_api.models import MarketDataSnapshot
from .market_data_quality import validate_candles


def _as_utc_datetime(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=dt_timezone.utc)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Snapshot candle timestamps must be present.")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Snapshot candle timestamps must include a timezone.")
    return parsed.astimezone(dt_timezone.utc)


def _canonicalize_candles(candles):
    """Return JSON-safe candle data with stable key ordering for deterministic hashes."""
    try:
        payload = json.loads(
            json.dumps(candles, sort_keys=True, separators=(",", ":"), allow_nan=False)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Candle data must be finite JSON-compatible values.") from exc
    validate_candles(payload)
    return payload


@transaction.atomic
def create_market_data_snapshot(owner, symbol, timeframe, candles, metadata=None):
    """Create or reuse an immutable snapshot for an exact candle payload.

    Identical data for the same owner/symbol/timeframe is deduplicated. The
    retrieved_at value records the first capture; later duplicate requests do
    not rewrite the original snapshot or its provenance.
    """
    if owner is None or not getattr(owner, "pk", None):
        raise ValueError("An authenticated owner is required for a market-data snapshot.")
    normalized_symbol = str(symbol).replace("/", "").replace("_", "").replace("-", "").upper()
    if not normalized_symbol:
        raise ValueError("A symbol is required for a market-data snapshot.")

    payload = _canonicalize_candles(candles)
    validation = validate_candles(payload)
    first_value = payload[0].get("time", payload[0].get("timestamp"))
    last_value = payload[-1].get("time", payload[-1].get("timestamp"))
    source = validation["source"]
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()

    snapshot, _created = MarketDataSnapshot.objects.get_or_create(
        owner=owner,
        symbol=normalized_symbol,
        timeframe=timeframe,
        content_sha256=digest,
        defaults={
            "source": source,
            "first_bar_at": _as_utc_datetime(first_value),
            "last_bar_at": _as_utc_datetime(last_value),
            "candle_count": len(payload),
            "retrieved_at": timezone.now(),
            "candles": payload,
            "validation_report": validation,
            "metadata": metadata or {},
        },
    )
    return snapshot
