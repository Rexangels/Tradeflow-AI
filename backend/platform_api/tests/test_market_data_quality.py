from django.test import SimpleTestCase

from platform_api.services.market_data_quality import (
    MarketDataQualityError,
    validate_candles,
)


def make_candle(timestamp, **overrides):
    candle = {
        "time": timestamp,
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 103.0,
        "volume": 1200.0,
        "source": "fixture",
    }
    candle.update(overrides)
    return candle


class MarketDataQualityTests(SimpleTestCase):
    def test_accepts_valid_ordered_batch(self):
        result = validate_candles([
            make_candle("2026-01-01T10:00:00+00:00"),
            make_candle("2026-01-01T11:00:00+00:00"),
        ])
        self.assertTrue(result["valid"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["source"], "fixture")

    def test_rejects_empty_batch(self):
        with self.assertRaises(MarketDataQualityError):
            validate_candles([])

    def test_rejects_non_positive_prices_and_invalid_ohlc(self):
        invalid = [
            make_candle("2026-01-01T10:00:00+00:00", close=0),
            make_candle("2026-01-01T10:00:00+00:00", high=101),
        ]
        for candle in invalid:
            with self.subTest(candle=candle):
                with self.assertRaises(MarketDataQualityError):
                    validate_candles([candle])

    def test_rejects_negative_and_non_finite_volume(self):
        for volume in (-1, float("nan"), float("inf")):
            with self.subTest(volume=volume):
                with self.assertRaises(MarketDataQualityError):
                    validate_candles([
                        make_candle("2026-01-01T10:00:00+00:00", volume=volume)
                    ])

    def test_rejects_duplicate_and_out_of_order_timestamps(self):
        batches = [
            [
                make_candle("2026-01-01T10:00:00+00:00"),
                make_candle("2026-01-01T10:00:00+00:00"),
            ],
            [
                make_candle("2026-01-01T11:00:00+00:00"),
                make_candle("2026-01-01T10:00:00+00:00"),
            ],
        ]
        for batch in batches:
            with self.subTest(batch=batch):
                with self.assertRaises(MarketDataQualityError):
                    validate_candles(batch)

    def test_rejects_timezone_naive_timestamp(self):
        with self.assertRaises(MarketDataQualityError):
            validate_candles([make_candle("2026-01-01T10:00:00")])
