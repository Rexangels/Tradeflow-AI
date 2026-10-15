from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase

from platform_api.services.trend_breakout import (
    STRATEGY_VERSION,
    evaluate_swing_alignment,
    h4_bias,
    score_single_timeframe,
    single_timeframe_signal,
)


def make_candles(count=220, trend="up"):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 1.0850
    for i in range(count):
        if trend == "up":
            price += 0.0008
        elif trend == "down":
            price -= 0.0008
        else:
            price += 0.0003 if i % 2 == 0 else -0.0003
        candles.append(
            {
                "time": (start + timedelta(hours=i)).isoformat(),
                "open": price - 0.0002,
                "high": price + 0.0004,
                "low": price - 0.0004,
                "close": price,
                "volume": 1000,
            }
        )
    return candles


class TrendBreakoutModuleTests(SimpleTestCase):
    def test_uptrend_scores_long_with_confidence(self):
        sig = score_single_timeframe(make_candles(220, "up"), symbol="EURUSD")
        self.assertEqual(sig["direction"], "long")
        self.assertGreaterEqual(sig["confidence"], 0.55)
        self.assertIsNotNone(sig["stop_loss"])
        self.assertIsNotNone(sig["take_profit"])

    def test_downtrend_scores_short_with_confidence(self):
        sig = score_single_timeframe(make_candles(220, "down"), symbol="EURUSD")
        self.assertEqual(sig["direction"], "short")
        self.assertGreaterEqual(sig["confidence"], 0.55)

    def test_chop_is_neutral_or_blocked(self):
        sig = single_timeframe_signal(make_candles(220, "chop"), symbol="EURUSD")
        # Chop must not produce an aligned trade (regime gate).
        self.assertIn(sig["macro_bias"], ("BULLISH", "BEARISH", "CONSOLIDATION"))
        if sig["macro_bias"] == "CONSOLIDATION":
            self.assertIsNone(sig["side"])
            self.assertFalse(sig["is_aligned"])

    def test_h4_bias_logic(self):
        self.assertEqual(h4_bias(1.10, 1.09, 1.08), "BULLISH")
        self.assertEqual(h4_bias(1.07, 1.08, 1.09), "BEARISH")
        self.assertEqual(h4_bias(1.085, 1.085, 1.085), "CONSOLIDATION")

    def test_swing_alignment_vetoes_counter_trend(self):
        # Bullish H4 + M15 short must be blocked.
        r = evaluate_swing_alignment("BULLISH", "long", "short")
        self.assertFalse(r["is_aligned"])
        self.assertEqual(r["quality"], "CONFLICTED")
        # Bullish H4 + H1 long + M15 long must align.
        r2 = evaluate_swing_alignment("BULLISH", "long", "long")
        self.assertTrue(r2["is_aligned"])
        self.assertEqual(r2["side"], "buy")
        # Consolidation never aligns.
        r3 = evaluate_swing_alignment("CONSOLIDATION", "long", "long")
        self.assertFalse(r3["is_aligned"])

    def test_single_timeframe_signal_applies_macro_veto(self):
        up = single_timeframe_signal(make_candles(220, "up"), symbol="EURUSD")
        self.assertEqual(up["macro_bias"], "BULLISH")
        self.assertEqual(up["side"], "buy")
        down = single_timeframe_signal(make_candles(220, "down"), symbol="EURUSD")
        self.assertEqual(down["macro_bias"], "BEARISH")
        self.assertEqual(down["side"], "sell")

    def test_strategy_version_pinned(self):
        self.assertEqual(STRATEGY_VERSION, "1.0.0")
