from urllib.error import URLError
from unittest.mock import patch

from django.test import TestCase, override_settings

from platform_api.models import MarketDataCache
from platform_api.services.market_data import get_candles


class StubResponse:
    def __init__(self, payload: str):
        self.payload = payload.encode("utf-8")

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class MarketDataServiceTests(TestCase):
    @patch("platform_api.services.market_data.urlopen")
    def test_get_candles_normalizes_binance_timestamps_to_utc(self, mock_urlopen):
        mock_urlopen.return_value = StubResponse(
            '[[1712275200000,"100.0","105.0","99.0","103.0","1500.0"]]'
        )

        candles = get_candles("BTCUSDT", "1h", limit=1, force_refresh=True)

        self.assertEqual(len(candles), 1)
        self.assertTrue(candles[0]["time"].endswith("+00:00"))
        self.assertEqual(candles[0]["close"], 103.0)

    @patch("platform_api.services.market_data.urlopen", side_effect=URLError("offline"))
    def test_get_candles_falls_back_to_cached_payload_when_fetch_fails(self, _mock_urlopen):
        cached_payload = [
            {
                "time": "2026-01-01T00:00:00+00:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 500.0,
            }
        ]
        MarketDataCache.objects.create(
            symbol="BTCUSDT",
            timeframe="1h",
            limit=2,
            payload=cached_payload,
        )

        candles = get_candles("BTCUSDT", "1h", limit=2, force_refresh=True)

        self.assertEqual(candles, cached_payload)

    @override_settings(MARKET_DATA_FALLBACK_MODE="synthetic")
    @patch("platform_api.services.market_data.urlopen", side_effect=URLError("offline"))
    def test_get_candles_generates_synthetic_payload_when_enabled(self, _mock_urlopen):
        candles = get_candles("BTCUSDT", "1h", limit=5, force_refresh=True)

        self.assertEqual(len(candles), 5)
        self.assertIn("time", candles[0])
        self.assertGreater(candles[-1]["close"], 0)

    @override_settings(MARKET_DATA_FALLBACK_MODE="synthetic")
    @patch("platform_api.services.market_data.urlopen", side_effect=URLError("offline"))
    def test_synthetic_payload_contains_mixed_bullish_and_bearish_candles(self, _mock_urlopen):
        candles = get_candles("ETHUSDT", "1h", limit=40, force_refresh=True)

        bullish = [candle for candle in candles if candle["close"] >= candle["open"]]
        bearish = [candle for candle in candles if candle["close"] < candle["open"]]
        self.assertTrue(bullish)
        self.assertTrue(bearish)
