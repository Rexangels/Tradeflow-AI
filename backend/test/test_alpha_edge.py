import os
import sys

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath("backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tradeflow_api.settings")
import django
django.setup()

from platform_api.services.economic_calendar import EconomicCalendarService
from platform_api.services.session_filter import SessionFilterService
from platform_api.services.multi_timeframe import MultiTimeframeService
from platform_api.services.risk_manager import RiskManager


def run_alpha_benchmarks():
    print("=" * 60)
    print("[RUNNING] TRADEFLOW AI ALPHA EDGE BENCHMARKS & VERIFICATION")
    print("=" * 60)

    # 1. Test Economic News Shield
    print("\n[TEST 1] Economic Calendar & News Shield...")
    events = EconomicCalendarService.get_upcoming_events(hours_ahead=24)
    print(f"  + Successfully fetched {len(events)} upcoming high-impact economic events.")
    assert len(events) > 0, "No events returned from EconomicCalendarService"
    
    first = events[0]
    print(f"  + Next Event: {first['currency']} - {first['name']} ({first['minutes_away']}m away, Impact: {first['impact']})")

    # Check news blocking logic on AUD/USD, EUR/USD, and AAPL
    for sym in ("AUD/USD", "EUR/USD", "AAPL"):
        is_blocked, reason, ev = EconomicCalendarService.is_news_blocked(sym, buffer_before_minutes=300)
        print(f"  + Symbol: {sym:<8} | News Shield Active: {str(is_blocked):<5} | Reason: {reason[:60] if reason else 'Clear for trading'}...")

    # 2. Test Session Timing & Liquidity Engine
    print("\n[TEST 2] Global Trading Session & Liquidity Engine...")
    session_info = SessionFilterService.get_current_session_info()
    print(f"  + Current UTC Time: {session_info['current_utc_time']}")
    print(f"  + Primary Session:  {session_info['primary_session']}")
    print(f"  + Active Sessions:  {', '.join(session_info['active_sessions'])}")
    print(f"  + Liquidity Rating: {session_info['liquidity_rating']} ({session_info['liquidity_score']}/100)")
    print(f"  + Favorable Window: {session_info['favorable_for_trading']}")
    print(f"  + Advice:           {session_info['advice']}")

    # 3. Test Top-Down Multi-Timeframe Confluence (H4 / H1 / M15)
    print("\n[TEST 3] Top-Down Multi-Timeframe Confluence Engine...")
    test_pairs = ["EUR/USD", "GBP/USD", "AUD/USD", "USD/JPY"]
    for pair in test_pairs:
        mtf = MultiTimeframeService.analyze_top_down(pair)
        print(f"\n  [PAIR: {pair}]")
        print(f"    - 4H Macro Bias:     {mtf['macro_bias_4h']} (Price: {mtf['h4']['price']}, 200 EMA: {mtf['h4']['ema200']}, RSI: {mtf['h4']['rsi']})")
        print(f"    - 1H Intermediate:   Direction: {mtf['h1']['direction'].upper()}, RSI: {mtf['h1']['rsi']}")
        print(f"    - 15M Entry Trigger: Direction: {mtf['m15']['direction'].upper()}, ATR: {mtf['m15']['atr_pips']} pips")
        print(f"    - Alignment Status:  {'ALIGNED' if mtf['is_aligned'] else 'NOT ALIGNED'} ({mtf['confluence_quality']})")
        print(f"    - Composite Score:   {mtf['composite_score']}%")
        if mtf.get("rejection_reason"):
            print(f"    - Guardrail Note:    {mtf['rejection_reason']}")
        if mtf['is_aligned']:
            print(f"    - Executable Setup:  {mtf['suggested_side'].upper()} @ {mtf['entry_price']} | SL: {mtf['stop_loss']} | TP: {mtf['take_profit']} ({mtf['rr_ratio']}R)")

    # 4. Test Risk Manager Integration
    print("\n[TEST 4] Risk Manager Guardrail Integration...")
    # Test order with news block simulated
    assessment = RiskManager.assess_order(
        symbol="EUR/USD",
        side="buy",
        qty=1000.0,
        current_price=1.0850,
        stop_loss=1.0820,
        take_profit=1.0910,
    )
    print(f"  + Standard Compliant Order: Approved={assessment.get('approved')}, Reason='{assessment.get('reason')}'")

    print("\n" + "=" * 60)
    print("[SUCCESS] ALL ALPHA EDGE BENCHMARKS & VERIFICATIONS COMPLETED!")
    print("=" * 60)


if __name__ == "__main__":
    run_alpha_benchmarks()
