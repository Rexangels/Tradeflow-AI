from datetime import datetime, timezone
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from platform_api.models import MarketDataSnapshot
from platform_api.services.market_data_snapshots import create_market_data_snapshot
from platform_api.views import MarketDataSnapshotDetailView, MarketDataSnapshotsView


def make_candles(close=103.0):
    return [
        {
            "time": "2026-01-01T10:00:00+00:00",
            "open": 100.0,
            "high": 105.0,
            "low": 98.0,
            "close": 102.0,
            "volume": 1200.0,
            "source": "mt5",
        },
        {
            "time": "2026-01-01T11:00:00+00:00",
            "open": 102.0,
            "high": 106.0,
            "low": 101.0,
            "close": close,
            "volume": 1300.0,
            "source": "mt5",
        },
    ]


class MarketDataSnapshotServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="operator",
            email=settings.DJANGO_ADMIN_EMAIL,
            password="not-used-in-this-test",
        )

    def test_identical_payload_is_deduplicated_and_first_metadata_is_preserved(self):
        candles = make_candles()
        first = create_market_data_snapshot(
            self.owner,
            "EUR/USD",
            "1h",
            candles,
            metadata={"origin": "provider_fetch"},
        )
        second = create_market_data_snapshot(
            self.owner,
            "EURUSD",
            "1h",
            candles,
            metadata={"origin": "request_supplied"},
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(MarketDataSnapshot.objects.count(), 1)
        self.assertEqual(first.content_sha256, second.content_sha256)
        self.assertEqual(second.metadata["origin"], "provider_fetch")
        self.assertEqual(second.candle_count, 2)
        self.assertEqual(second.source, "mt5")

    def test_changed_candle_content_creates_a_new_snapshot(self):
        first = create_market_data_snapshot(self.owner, "EURUSD", "1h", make_candles())
        second = create_market_data_snapshot(self.owner, "EURUSD", "1h", make_candles(close=104.0))

        self.assertNotEqual(first.content_sha256, second.content_sha256)
        self.assertEqual(MarketDataSnapshot.objects.count(), 2)

    def test_invalid_data_is_rejected_before_persistence(self):
        candles = make_candles()
        candles[1]["close"] = float("nan")

        with self.assertRaises(ValueError):
            create_market_data_snapshot(self.owner, "EURUSD", "1h", candles)

        self.assertEqual(MarketDataSnapshot.objects.count(), 0)

    def test_timestamps_are_persisted_in_utc(self):
        snapshot = create_market_data_snapshot(self.owner, "EURUSD", "1h", make_candles())
        self.assertEqual(snapshot.first_bar_at, datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(snapshot.last_bar_at, datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc))


class MarketDataSnapshotApiTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = User.objects.create_user(
            username="admin",
            email=settings.DJANGO_ADMIN_EMAIL,
            password="not-used-in-this-test",
        )
        self.other = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="not-used-in-this-test",
        )
        self.snapshot = create_market_data_snapshot(
            self.owner,
            "EURUSD",
            "1h",
            make_candles(),
            metadata={"origin": "provider_fetch"},
        )
        self.other_snapshot = create_market_data_snapshot(
            self.other,
            "GBPUSD",
            "1h",
            make_candles(),
        )

    def test_list_is_scoped_to_authenticated_owner(self):
        request = self.factory.get("/api/v1/market-data/snapshots")
        force_authenticate(request, user=self.owner)

        response = MarketDataSnapshotsView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(self.snapshot.id))
        self.assertNotIn("candles", response.data[0])

    def test_detail_returns_exact_candles_for_owner(self):
        request = self.factory.get(f"/api/v1/market-data/snapshots/{self.snapshot.id}")
        force_authenticate(request, user=self.owner)

        response = MarketDataSnapshotDetailView.as_view()(request, snapshot_id=self.snapshot.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["contentSha256"], self.snapshot.content_sha256)
        self.assertEqual(response.data["candles"], self.snapshot.candles)

    def test_detail_does_not_expose_another_owners_snapshot(self):
        request = self.factory.get(f"/api/v1/market-data/snapshots/{self.other_snapshot.id}")
        force_authenticate(request, user=self.owner)

        response = MarketDataSnapshotDetailView.as_view()(request, snapshot_id=self.other_snapshot.id)

        self.assertEqual(response.status_code, 404)
