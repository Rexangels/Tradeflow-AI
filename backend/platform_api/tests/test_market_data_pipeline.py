import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings

from platform_api.models import MarketDataCache
from platform_api.services import market_data
from platform_api.services.market_data_quality import MarketDataQualityError


def make_candle(timestamp, **overrides):
    candle = {
        "time": timestamp,
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 103.0,
        "volume": 1200.0,
    }
    candle.update(overrides)
    return candle


class MarketDataDiagnosticsTests(SimpleTestCase):
    def test_reports_gaps_without_repairing_data(self):
        now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        candles = [
            make_candle("2026-01-01T10:00:00+00:00"),
            make_candle("2026-01-01T10:03:00+00:00"),
        ]
        report = market_data.market_data_quality_report(candles, "1m", now=now)
        self.assertEqual(report["gap_count"], 1)
        self.assertEqual(report["missing_intervals_estimate"], 2)
        self.assertEqual(report["freshness"], "stale")
        self.assertEqual(len(candles), 2)

    def test_reports_recent_data(self):
        now = datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc)
        candles = [make_candle("2026-01-01T10:00:00+00:00")]
        report = market_data.market_data_quality_report(candles, "1m", now=now)
        self.assertEqual(report["freshness"], "recent")
        self.assertEqual(report["gap_count"], 0)


class MarketDataPipelineTests(TestCase):
    def setUp(self):
        self.valid = [
            make_candle("2026-01-01T10:00:00+00:00"),
            make_candle("2026-01-01T11:00:00+00:00"),
        ]

    @override_settings(MARKET_DATA_FALLBACK_MODE="strict")
    @patch("platform_api.services.market_data._fetch_alpaca_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_mt5_bars")
    def test_valid_provider_batch_is_validated_tagged_and_cached(self, fetch_mt5, _fetch_alpaca):
        fetch_mt5.return_value = self.valid
        result = market_data.get_candles("EURUSD", "1h", limit=2, force_refresh=True)
        self.assertEqual(result[0]["source"], "mt5")
        cached = MarketDataCache.objects.get(symbol="EURUSD", timeframe="1h", limit=2)
        self.assertEqual(cached.payload, result)

    @override_settings(MARKET_DATA_FALLBACK_MODE="strict")
    @patch("platform_api.services.market_data._fetch_alpaca_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_mt5_bars")
    def test_invalid_provider_batch_is_not_cached(self, fetch_mt5, _fetch_alpaca):
        fetch_mt5.return_value = [make_candle("2026-01-01T10:00:00", close=float("nan"))]
        with self.assertRaises(market_data.MarketDataUnavailableError):
            market_data.get_candles("EURUSD", "1h", limit=1, force_refresh=True)
        self.assertFalse(MarketDataCache.objects.filter(symbol="EURUSD").exists())

    @override_settings(MARKET_DATA_FALLBACK_MODE="strict")
    @patch("platform_api.services.market_data._fetch_alpaca_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_mt5_bars")
    def test_invalid_cached_payload_is_ignored_and_refetched(self, fetch_mt5, _fetch_alpaca):
        MarketDataCache.objects.create(
            symbol="EURUSD",
            timeframe="1h",
            limit=2,
            payload=[make_candle("2026-01-01T10:00:00", close=0)],
        )
        fetch_mt5.return_value = self.valid
        result = market_data.get_candles("EURUSD", "1h", limit=2)
        self.assertEqual(result[0]["source"], "mt5")
        self.assertEqual(MarketDataCache.objects.get(symbol="EURUSD").payload, result)

    @patch("platform_api.services.mt5_client.get_mt5_client")
    def test_mt5_does_not_fallback_to_forming_bar_when_completed_bar_missing(self, get_client):
        client = MagicMock()
        client.is_connected.return_value = True
        client._resolve_symbol.return_value = "EURUSD"
        get_client.return_value = client

        mt5_mock = MagicMock()
        mt5_mock.TIMEFRAME_M1 = 1
        mt5_mock.TIMEFRAME_M5 = 5
        mt5_mock.TIMEFRAME_M15 = 15
        mt5_mock.TIMEFRAME_H1 = 60
        mt5_mock.TIMEFRAME_H4 = 240
        mt5_mock.TIMEFRAME_D1 = 1440
        mt5_mock.copy_rates_from_pos.return_value = None

        with patch.dict(sys.modules, {"MetaTrader5": mt5_mock}):
            result = market_data._fetch_mt5_bars("EURUSD", "1h", 10)

        self.assertEqual(result, [])
        mt5_mock.copy_rates_from_pos.assert_called_once_with("EURUSD", 60, 1, 10)
