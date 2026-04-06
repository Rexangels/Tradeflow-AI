from math import isclose, isnan

from django.test import SimpleTestCase

from platform_api.services.indicators import (
    calculate_bollinger_bands,
    calculate_ema,
    calculate_rsi,
    calculate_sma,
)


class IndicatorTests(SimpleTestCase):
    def test_sma_returns_expected_windowed_values(self):
        values = [1, 2, 3, 4, 5]

        result = calculate_sma(values, 3)

        self.assertTrue(isnan(result[0]))
        self.assertTrue(isnan(result[1]))
        self.assertEqual(result[2:], [2.0, 3.0, 4.0])

    def test_ema_returns_expected_sequence_for_small_series(self):
        values = [10, 11, 12, 13]

        result = calculate_ema(values, 3)

        expected = [10.0, 10.5, 11.25, 12.125]
        for actual, target in zip(result, expected):
            self.assertTrue(isclose(actual, target, rel_tol=1e-9))

    def test_rsi_reaches_extremes_for_monotonic_moves(self):
        rising = list(range(1, 21))
        falling = list(range(20, 0, -1))

        rising_rsi = calculate_rsi(rising, 14)
        falling_rsi = calculate_rsi(falling, 14)

        self.assertEqual(rising_rsi[-1], 100)
        self.assertEqual(falling_rsi[-1], 0)

    def test_bollinger_bands_collapse_on_constant_series(self):
        values = [50.0] * 25

        middle, upper, lower = calculate_bollinger_bands(values, 20, 2)

        self.assertEqual(middle[-1], 50.0)
        self.assertEqual(upper[-1], 50.0)
        self.assertEqual(lower[-1], 50.0)
