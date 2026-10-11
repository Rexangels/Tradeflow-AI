from unittest.mock import patch

from django.test import TestCase, override_settings

from platform_api.models import MarketDataCache
from platform_api.services.market_data import MarketDataUnavailableError, get_candles


class MarketDataServiceTests(TestCase):
    @patch("platform_api.services.market_data._fetch_mt5_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_alpaca_bars")
    def test_get_candles_marks_provider_payload(self, mock_alpaca, _mock_mt5):
        mock_alpaca.return_value = [{
            "time": "2026-01-01T00:00:00+00:00", "open": 100.0,
            "high": 105.0, "low": 99.0, "close": 103.0, "volume": 1500.0,
        }]

        candles = get_candles("BTCUSDT", "1h", limit=1, force_refresh=True)

        self.assertEqual(len(candles), 1)
        self.assertTrue(candles[0]["time"].endswith("+00:00"))
        self.assertEqual(candles[0]["close"], 103.0)
        self.assertEqual(candles[0]["source"], "alpaca")

    @override_settings(MARKET_DATA_FALLBACK_MODE="synthetic")
    @patch("platform_api.services.market_data._fetch_mt5_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_alpaca_bars", return_value=[])
    def test_get_candles_falls_back_to_cached_payload_when_fetch_fails(self, _mock_alpaca, _mock_mt5):
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
    @patch("platform_api.services.market_data._fetch_mt5_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_alpaca_bars", return_value=[])
    def test_get_candles_generates_synthetic_payload_when_enabled(self, _mock_alpaca, _mock_mt5):
        candles = get_candles("BTCUSDT", "1h", limit=5, force_refresh=True)

        self.assertEqual(len(candles), 5)
        self.assertIn("time", candles[0])
        self.assertGreater(candles[-1]["close"], 0)

    @override_settings(MARKET_DATA_FALLBACK_MODE="synthetic")
    @patch("platform_api.services.market_data._fetch_mt5_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_alpaca_bars", return_value=[])
    def test_synthetic_payload_contains_mixed_bullish_and_bearish_candles(self, _mock_alpaca, _mock_mt5):
        candles = get_candles("ETHUSDT", "1h", limit=40, force_refresh=True)

        bullish = [candle for candle in candles if candle["close"] >= candle["open"]]
        bearish = [candle for candle in candles if candle["close"] < candle["open"]]
        self.assertTrue(bullish)
        self.assertTrue(bearish)

    @override_settings(MARKET_DATA_FALLBACK_MODE="synthetic")
    @patch("platform_api.services.market_data._fetch_alpaca_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_mt5_bars", return_value=[])
    def test_synthetic_candles_are_explicitly_labelled(self, _mock_mt5, _mock_alpaca):
        candles = get_candles("BTCUSDT", "1h", limit=5, force_refresh=True)

        self.assertEqual({candle["source"] for candle in candles}, {"synthetic_demo"})

    @override_settings(MARKET_DATA_FALLBACK_MODE="strict")
    @patch("platform_api.services.market_data._fetch_alpaca_bars", return_value=[])
    @patch("platform_api.services.market_data._fetch_mt5_bars", return_value=[])
    def test_strict_mode_rejects_unavailable_real_data(self, _mock_mt5, _mock_alpaca):
        with self.assertRaises(MarketDataUnavailableError):
            get_candles("BTCUSDT", "1h", limit=5, force_refresh=True)
