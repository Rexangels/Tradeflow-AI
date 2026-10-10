from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from django.conf import settings
from django.utils import timezone

try:
    from google import genai
except ImportError:  # pragma: no cover
    genai = None

from platform_api.defaults import DEFAULT_AGENT
from platform_api.models import (
    Agent,
    AISignal,
    BacktestRun,
    ChatMessage,
    ChatThread,
    ForexPairConfig,
    TradeLog,
    UsageEvent,
)
from platform_api.presenters import serialize_backtest, serialize_chat_message
from .backtests import run_backtest
from .indicators import analyze_forex_confluence
from .market_data import (
    format_display_symbol,
    get_candles,
    get_forex_quote,
    latest_price,
    normalize_symbol,
)
from .order_execution import OrderExecutionService
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)

FOREX_PAIRS_SET = {
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    "EURGBP", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "EURAUD", "EURCAD",
    "GBPAUD", "GBPCAD",
}


@dataclass
class ToolContext:
    name: str
    content: str


def handle_chat(user, payload: dict[str, Any]) -> dict[str, Any]:
    thread = _resolve_thread(user, payload)
    user_msg = payload["message"]
    ChatMessage.objects.create(thread=thread, role="user", content=user_msg)

    # 1. Check for explicit trade execution intent (e.g., "buy EUR/USD", "close position", "let buy it")
    execution_result = _handle_trade_intents(user, thread, user_msg)
    if execution_result:
        ChatMessage.objects.create(
            thread=thread,
            role="tool",
            content=execution_result["summary"],
            metadata={"tool": "order_execution", "result": execution_result},
        )

    # 2. Collect rich market, technical, risk, and account contexts
    contexts = _collect_contexts(user, payload, thread=thread)
    if execution_result:
        contexts.insert(0, ToolContext(name="order_execution_result", content=execution_result["summary"]))

    for context in contexts:
        if context.name == "order_execution_result":
            continue  # Already saved to ChatMessage above to avoid duplicate messages!
        ChatMessage.objects.create(
            thread=thread,
            role="tool",
            content=context.content,
            metadata={"tool": context.name},
        )

    # 3. Generate AI response (using Gemini if configured, or synthesized research brief)
    reply = _generate_reply(thread, user_msg, contexts)
    ChatMessage.objects.create(thread=thread, role="assistant", content=reply)

    UsageEvent.objects.create(
        owner=user,
        category="ai_message",
        reference_id=str(thread.id),
        quantity=1,
        metadata={"threadId": str(thread.id)},
    )

    messages = [serialize_chat_message(message) for message in thread.messages.order_by("created_at")]
    return {"threadId": str(thread.id), "reply": reply, "messages": messages}


def run_agent_cycle(user, agent: Optional[Agent] = None, symbol: Optional[str] = None, auto_trade: bool = False) -> dict[str, Any]:
    """
    Automated decision cycle:
    1. Observe: scan watched forex pairs & Alpaca account state
    2. Analyze: compute technical confluence (RSI, MACD, EMA, ATR, BB)
    3. Assess Risk: evaluate risk rules, compute suggested position size & SL/TP
    4. Decide: log AISignal
    5. Execute: place bracket trade on Alpaca if auto_trade=True and confidence >= 60%
    """
    if not agent:
        agent = Agent.objects.filter(owner=user).first()
        if not agent:
            agent = Agent.objects.create(
                owner=user,
                name="Alpha Trend Agent",
                type="trend_following",
                reward_style="sharpe",
                risk_tolerance=0.02,
                holding_behavior="swing",
                strategies=[{"name": "Forex Confluence", "enabled": True}],
            )

    client_mode = OrderExecutionService.get_account_overview()
    symbols_to_scan = [symbol] if symbol else [p.symbol for p in ForexPairConfig.objects.filter(is_watched=True)]
    if not symbols_to_scan:
        symbols_to_scan = ["EUR/USD", "GBP/USD", "USD/JPY"]

    cycle_signals = []
    executed_trades = []

    from .multi_timeframe import MultiTimeframeService
    from .economic_calendar import EconomicCalendarService
    from .session_filter import SessionFilterService

    session_info = SessionFilterService.get_current_session_info()

    for sym in symbols_to_scan:
        mtf = MultiTimeframeService.analyze_top_down(sym)
        is_aligned = mtf["is_aligned"]
        direction = "long" if mtf["macro_bias_4h"] == "BULLISH" and is_aligned else ("short" if mtf["macro_bias_4h"] == "BEARISH" and is_aligned else "neutral")
        confidence = mtf["composite_score"] / 100.0
        suggested_side = mtf["suggested_side"]

        # Check news shield
        is_news_blocked, news_reason, news_event = EconomicCalendarService.is_news_blocked(sym)

        reasoning_parts = [
            f"4H Macro: {mtf['macro_bias_4h']}",
            f"Alignment: {mtf['confluence_quality']}",
            f"Session: {session_info['primary_session']} ({session_info['liquidity_rating']})",
        ]
        if mtf.get("rejection_reason"):
            reasoning_parts.append(mtf["rejection_reason"])
        if is_news_blocked:
            reasoning_parts.append(f"NEWS SHIELD ACTIVE: {news_reason}")

        # Record AISignal in database
        sig_record = None
        if agent:
            sig_record = AISignal.objects.create(
                agent=agent,
                symbol=sym,
                timeframe="4h+1h+15m",
                direction=direction,
                confidence=confidence,
                reasoning=" | ".join(reasoning_parts),
                indicators={
                    "macro_bias_4h": mtf["macro_bias_4h"],
                    "confluence_quality": mtf["confluence_quality"],
                    "h4_rsi": mtf["h4"]["rsi"],
                    "h1_rsi": mtf["h1"]["rsi"],
                    "m15_rsi": mtf["m15"]["rsi"],
                    "composite_score": mtf["composite_score"],
                    "news_blocked": is_news_blocked,
                },
                acted_on=False,
            )

        cycle_signals.append({
            "symbol": sym,
            "direction": direction,
            "confidence": confidence,
            "confidence_pct": round(mtf["composite_score"], 1),
            "macro_bias_4h": mtf["macro_bias_4h"],
            "confluence_quality": mtf["confluence_quality"],
            "is_aligned": is_aligned,
            "suggested_side": suggested_side,
            "current_price": mtf["entry_price"],
            "stop_loss": mtf["stop_loss"],
            "take_profit": mtf["take_profit"],
            "rr_ratio": mtf["rr_ratio"],
            "news_blocked": is_news_blocked,
            "reasons": reasoning_parts,
        })

        # Autonomous execution trigger: Requires Top-Down alignment + No news block + Good session
        can_auto_trade = (
            auto_trade
            and is_aligned
            and direction in {"long", "short"}
            and confidence >= 0.65
            and not is_news_blocked
            and session_info["favorable_for_trading"]
        )

        if can_auto_trade and suggested_side:
            qty = 1000.0
            order_res = OrderExecutionService.execute_order(
                symbol=sym,
                side=suggested_side,
                qty=qty,
                stop_loss=mtf["stop_loss"],
                take_profit=mtf["take_profit"],
                agent=agent,
                ai_reasoning=(
                    f"Top-Down Institutional Cycle ({mtf['confluence_quality']}, {round(mtf['composite_score'], 1)}% score): "
                    f"4H {mtf['macro_bias_4h']} bias confirmed on M15 trigger. Session: {session_info['primary_session']}."
                ),
            )
            if order_res.get("success"):
                executed_trades.append(order_res)
                if sig_record:
                    sig_record.acted_on = True
                    trade_log_id = order_res.get("trade_log_id")
                    if trade_log_id:
                        sig_record.trade_log = TradeLog.objects.filter(id=trade_log_id).first()
                    sig_record.save()

    return {
        "timestamp": timezone.now().isoformat(),
        "account": client_mode,
        "scanned_pairs_count": len(symbols_to_scan),
        "signals": cycle_signals,
        "executed_trades": executed_trades,
    }


def _guess_symbol_from_text(message: str) -> Optional[str]:
    if not message:
        return None
    clean_msg = message.strip()
    STOP_WORDS = {
        "IT", "THIS", "THAT", "THE", "NOW", "TRADE", "ORDER", "POSITION",
        "LOT", "LOTS", "UNITS", "SOME", "MORE", "PAIR", "FOR", "ON", "AT", "IN",
        "GOOD", "OK", "YES", "NO", "BUY", "SELL", "LONG", "SHORT", "HERE", "PLEASE"
    }
    if clean_msg.upper() in STOP_WORDS:
        return None

    # Check open positions first
    try:
        from .order_execution import OrderExecutionService
        open_pos = OrderExecutionService.get_open_positions()
        for p in open_pos:
            if p["symbol"].lower() in clean_msg.lower():
                return p["symbol"]
    except Exception:
        pass

    # Check crypto tickers and aliases first
    crypto_alias_map = {
        "BITCOIN": "BTC/USD",
        "BTC": "BTC/USD",
        "ETHEREUM": "ETH/USD",
        "ETH": "ETH/USD",
        "SOLANA": "SOL/USD",
        "SOL": "SOL/USD",
        "RIPPLE": "XRP/USD",
        "XRP": "XRP/USD",
        "DOGECOIN": "DOGE/USD",
        "DOGE": "DOGE/USD",
        "LITECOIN": "LTC/USD",
        "LTC": "LTC/USD",
        "CARDANO": "ADA/USD",
        "ADA": "ADA/USD",
        "BNB": "BNB/USD",
        "GOLD": "XAU/USD",
        "XAU": "XAU/USD",
        "SILVER": "XAG/USD",
        "XAG": "XAG/USD",
    }
    for kw, target in crypto_alias_map.items():
        if re.search(rf"\b{kw}\b", clean_msg.upper()):
            return target

    # Check forex pairs
    clean_upper = clean_msg.upper().replace("/", "")
    for pair in FOREX_PAIRS_SET:
        if pair in clean_upper:
            return format_display_symbol(pair)

    # Check common stock tickers
    for ticker in ("AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "SPY", "QQQ"):
        if re.search(rf"\b{ticker}\b", clean_msg.upper()):
            return ticker

    # Check slashed format like EUR/USD or SOL/USD
    match = re.search(r"\b([A-Z]{3,4})/([A-Z]{3})\b", clean_msg.upper())
    if match:
        return f"{match.group(1)}/{match.group(2)}"

    return None


def _get_last_discussed_symbol(thread: Optional[ChatThread]) -> Optional[str]:
    if not thread:
        return None
    try:
        recent = thread.messages.order_by("-created_at")[:12]
        for msg in recent:
            s = _guess_symbol_from_text(msg.content)
            if s:
                return s
    except Exception:
        pass
    return None


def _handle_trade_intents(user, thread: Any, message: str) -> Optional[dict[str, Any]]:
    """
    Parses natural language execution commands like:
    - 'buy 1000 EUR/USD'
    - 'buy 0.01 SOL/USD'
    - 'let buy it'
    - 'good execute this trade'
    - 'close position'
    """
    agent = thread.agent if isinstance(thread, ChatThread) else thread
    chat_thread = thread if isinstance(thread, ChatThread) else None
    msg = message.lower().strip()

    # Close positions intent
    if "close all" in msg or "liquidate all" in msg:
        client = OrderExecutionService.get_open_positions()
        closed_count = 0
        for p in client:
            OrderExecutionService.close_position(p["symbol"])
            closed_count += 1
        return {
            "action": "close_all",
            "summary": f"Liquidated {closed_count} open positions across the Alpaca account.",
        }

    # Trailing Stop intent: e.g. "trail AAPL by 5%" or "trailing stop AAPL 5%"
    trail_match = re.search(r"(?:trail|trailing\s*stop)\s+([a-zA-Z]{1,6}(?:/[a-zA-Z]{3})?)(?:\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*%?)?", msg)
    if trail_match:
        from .trade_monitor import TradeMonitorService
        t_sym = trail_match.group(1).upper()
        t_pct = float(trail_match.group(2)) if trail_match.group(2) else 5.0
        res = TradeMonitorService.apply_protection(t_sym, protect_type="trailing_stop", trail_percent=t_pct)
        if res.get("success"):
            return {
                "action": "trailing_stop",
                "summary": f"Activated AI {t_pct}% Trailing Stop on {t_sym}. Alpaca will dynamically trail price to lock in profits.",
            }
        return {"action": "trailing_stop", "summary": f"Could not set trailing stop on {t_sym}: {res.get('error')}"}

    # Breakeven / Protect intent: e.g. "protect AAPL" or "breakeven AAPL"
    if any(k in msg for k in ("breakeven", "break-even", "protect", "shield")):
        from .trade_monitor import TradeMonitorService
        try:
            open_pos = OrderExecutionService.get_open_positions()
            target = next((p["symbol"] for p in open_pos if p["symbol"].lower() in msg), None)
            if target:
                res = TradeMonitorService.apply_protection(target, protect_type="breakeven")
                if res.get("success"):
                    return {
                        "action": "breakeven",
                        "summary": f"Protected {target} with Zero-Risk Breakeven Stop! Stop loss moved above entry price to guarantee zero loss.",
                    }
                return {"action": "breakeven", "summary": f"Could not protect {target}: {res.get('error')}"}
        except Exception:
            pass

    close_match = re.search(r"close\s+([a-zA-Z]{1,6}(?:/[a-zA-Z]{3})?)", msg)
    if close_match:
        target_sym = close_match.group(1).replace(" ", "").upper()
        STOP_WORDS = {"IT", "THIS", "POSITION", "TRADE", "NOW"}
        if target_sym in STOP_WORDS:
            target_sym = _get_last_discussed_symbol(chat_thread) or "BTC/USD"
        res = OrderExecutionService.close_position(target_sym)
        if res.get("success"):
            return {
                "action": "close_position",
                "summary": f"Successfully closed position for {target_sym} at {res.get('closed_at_price')}.",
            }
        return {"action": "close_position", "summary": f"Could not close position for {target_sym}: {res.get('error')}"}

    # Guard against pure inquiry / analytical phrases so we don't accidentally execute when user asks questions
    inquiry_phrases = (
        "see if", "check if", "can we", "could we", "should we", "is it good",
        "is it safe", "can our ai", "can you", "what if", "how to", "why", "when to",
        "analyse", "analyze", "what crypto", "which pair"
    )
    is_inquiry = any(p in msg for p in inquiry_phrases)
    has_explicit_cmd = any(k in msg for k in ("now execute", "please execute", "go ahead and execute", "execute now", "place order now", "let buy", "let's buy", "lets buy", "buy it"))
    if is_inquiry and not has_explicit_cmd:
        return None

    # Check for trade execution intent
    # 1. Direct explicit buy/sell (e.g. "buy 0.01 lot EUR/USD", "buy eur/usd", "sell 0.01 EUR/USD", "let buy it", "buy it")
    trade_match = re.search(r"\b(buy|sell|long|short)\b(?:\s+([\d,.]+)\s*(?:lot|lots|units)?)?(?:\s+([a-zA-Z]{1,6}(?:/[a-zA-Z]{3})?))?", msg)
    # 2. General execution intent (e.g. "execute trade on EUR/USD", "enter trade", "place the trade", "take trade")
    exec_match = re.search(r"\b(execute|place|enter|open|take)\b.*?\b(trade|order|position)\b", msg)

    if trade_match or exec_match:
        side = None
        raw_qty = None
        raw_sym = None

        STOP_WORDS = {
            "IT", "THIS", "THAT", "THE", "NOW", "TRADE", "ORDER", "POSITION",
            "LOT", "LOTS", "UNITS", "SOME", "MORE", "PAIR", "FOR", "ON", "AT", "IN",
            "GOOD", "OK", "YES", "NO", "BUY", "SELL", "LONG", "SHORT", "HERE", "PLEASE"
        }

        if trade_match:
            raw_side = trade_match.group(1).lower()
            side = "buy" if raw_side in ("buy", "long") else "sell"
            raw_qty = trade_match.group(2)
            matched_sym = trade_match.group(3)
            if matched_sym and matched_sym.upper() in STOP_WORDS:
                matched_sym = None
            raw_sym = (_guess_symbol_from_text(matched_sym) if matched_sym else None) or _guess_symbol_from_text(message)
        else:
            raw_sym = _guess_symbol_from_text(message)

        if not raw_sym and chat_thread:
            raw_sym = _get_last_discussed_symbol(chat_thread)

        if not raw_sym:
            open_pos = OrderExecutionService.get_open_positions()
            raw_sym = open_pos[0]["symbol"] if open_pos else "BTC/USD"

        disp_sym = format_display_symbol(raw_sym)
        active_broker = OrderExecutionService.get_active_broker()

        # Parse lot / qty:
        lot_match = re.search(r"([\d,.]+)\s*(?:lot|lots)", msg)
        if lot_match:
            qty = float(lot_match.group(1))
        elif raw_qty:
            qty = float(raw_qty.replace(",", ""))
        else:
            qty = 0.01 if active_broker == "mt5" else 1000.0

        # If side is not specified (e.g. "execute trade on EUR/USD"), infer from top-down confluence:
        from .multi_timeframe import MultiTimeframeService
        mtf = MultiTimeframeService.analyze_top_down(disp_sym)

        if not side:
            if mtf.get("suggested_side"):
                side = mtf["suggested_side"].lower()
            else:
                return {
                    "action": "execute_order_needs_direction",
                    "summary": (
                        f"Cannot auto-execute {disp_sym}: Multi-timeframe confluence is {mtf['confluence_quality']} "
                        f"({mtf.get('rejection_reason', 'Neutral alignment')}). "
                        f"To execute anyway, please explicitly specify side, e.g. 'buy 0.01 {disp_sym}' or 'sell 0.01 {disp_sym}'."
                    ),
                }

        # Parse optional explicit SL / TP from prompt
        sl_match = re.search(r"(?:sl|stop\s*loss)[:\s]+([\d.]+)", msg)
        tp_match = re.search(r"(?:tp|take\s*profit)[:\s]+([\d.]+)", msg)

        sl = float(sl_match.group(1)) if sl_match else None
        tp = float(tp_match.group(1)) if tp_match else None

        # If not provided in prompt, use tight calculated SL / TP from top-down / ATR
        if not sl:
            sl = mtf.get("stop_loss")
            tp = tp or mtf.get("take_profit")
            if not sl:
                confluence = analyze_forex_confluence(disp_sym)
                sl = confluence.get("stop_loss")
                tp = tp or confluence.get("take_profit")

        # Sanity check stop loss geometry against live price to prevent risk engine rejection
        curr_px = latest_price(normalize_symbol(disp_sym))
        if sl is not None and curr_px:
            if side == "buy" and sl >= curr_px:
                sl = round(curr_px * 0.985, 2 if curr_px > 10 else 4)
            elif side == "sell" and sl <= curr_px:
                sl = round(curr_px * 1.015, 2 if curr_px > 10 else 4)

        if tp is not None and curr_px:
            if side == "buy" and tp <= curr_px:
                tp = round(curr_px * 1.03, 2 if curr_px > 10 else 4)
            elif side == "sell" and tp >= curr_px:
                tp = round(curr_px * 0.97, 2 if curr_px > 10 else 4)

        res = OrderExecutionService.execute_order(
            symbol=disp_sym,
            side=side,
            qty=qty,
            stop_loss=sl,
            take_profit=tp,
            agent=agent,
            ai_reasoning=f"Chat execution requested by user: '{message}'",
        )

        broker_name = res.get("broker") or ("MetaTrader 5 (Exness Demo)" if active_broker == "mt5" else "Alpaca Paper")
        vol_label = f"{res.get('volume', qty)} lot" if active_broker == "mt5" else f"{qty} units"

        if res.get("success"):
            order_id = res.get("order_id") or res.get("ticket")
            fill_px = res.get("entry_price")
            return {
                "action": "execute_order",
                "summary": (
                    f"Successfully placed {side.upper()} order for {vol_label} of {disp_sym} on {broker_name} "
                    f"at ~{fill_px}. Attached Stop-Loss: {sl}, Take-Profit: {tp}. Ticket/Order ID: #{order_id}."
                ),
                "details": res,
            }
        else:
            return {
                "action": "execute_order_rejected",
                "summary": f"Order for {disp_sym} on {broker_name} was rejected: {res.get('error')}",
                "details": res,
            }

    return None


def _resolve_thread(user, payload: dict[str, Any]) -> ChatThread:
    agent = None
    if payload.get("agentId"):
        agent = Agent.objects.filter(owner=user, id=payload["agentId"]).first()

    if payload.get("threadId"):
        return ChatThread.objects.get(id=payload["threadId"], owner=user)

    return ChatThread.objects.create(owner=user, agent=agent, title=payload["message"][:80])


def _collect_contexts(user, payload: dict[str, Any], thread: Optional[ChatThread] = None) -> list[ToolContext]:
    message = payload["message"].lower()
    contexts: list[ToolContext] = []

    # Priority: message symbol > thread symbol > payload symbol
    msg_sym = _guess_symbol_from_text(payload["message"])
    thread_sym = _get_last_discussed_symbol(thread) if (not msg_sym and thread) else None
    symbol = msg_sym or thread_sym or payload.get("symbol") or "BTC/USD"
    timeframe = payload.get("timeframe") or "1h"
    backtest_id = payload.get("backtestId")

    # 1. Live Active Broker Account & Risk Guardrails Context
    try:
        acc = OrderExecutionService.get_account_overview()
        active_broker = OrderExecutionService.get_active_broker()
        broker_label = "MetaTrader 5 (Exness Demo)" if active_broker == "mt5" else f"Alpaca ({acc.get('mode', 'paper').upper()})"
        rules = RiskManager.get_all_rules()
        positions = OrderExecutionService.get_open_positions()
        equity_val = acc.get("equity") or acc.get("balance") or 0.0
        free_margin = acc.get("marginFree") or acc.get("buying_power") or 0.0
        leverage_val = acc.get("leverage", 2000)

        contexts.append(
            ToolContext(
                name="active_broker_and_account",
                content=(
                    f"Active Broker Gateway: {broker_label}. "
                    f"Account Balance: ${acc.get('balance', equity_val):,.2f}, Equity: ${equity_val:,.2f}, "
                    f"Free Margin / Buying Power: ${free_margin:,.2f}, Leverage: 1:{leverage_val}. "
                    f"Open positions count: {len(positions)}. "
                    f"Enforced Risk Rules: Max Risk/Trade: {rules.get('max_risk_pct')}%, "
                    f"Daily Loss Limit: {rules.get('daily_loss_limit_pct')}%, "
                    f"Min R:R: {rules.get('min_rr_ratio')}R, Mandatory Stop-Loss: {rules.get('require_stop_loss')}."
                ),
            )
        )
        if positions:
            pos_summary = ", ".join(
                f"{p['symbol']} ({p['side'].upper()} {p.get('qty', p.get('volume'))}, entry {p.get('avg_entry_price', p.get('entry_price'))}, unrealized PnL: ${p['unrealized_pnl']:.2f})"
                for p in positions[:4]
            )
            contexts.append(ToolContext(name="open_positions", content=f"Current open positions: {pos_summary}"))
    except Exception as exc:
        logger.warning(f"Could not gather account context: {exc}")

    # 2. Forex & Crypto Market Data & Institutional Multi-Timeframe Confluence Context
    crypto_kws = ("crypto", "btc", "eth", "sol", "xrp", "doge", "ltc", "ada", "bnb", "bitcoin", "ethereum", "gold", "silver")
    all_kws = ("forex", "eur", "gbp", "jpy", "usd", "market", "price", "signal", "pair", "trade", "long", "short") + crypto_kws
    if symbol or any(kw in message for kw in all_kws):
        target_sym = symbol or "BTC/USD"
        try:
            quote = get_forex_quote(target_sym)
            contexts.append(
                ToolContext(
                    name="forex_market_quote",
                    content=(
                        f"Live Quote for {quote['symbol']}: Bid: {quote['bid']}, Ask: {quote['ask']}, Mid: {quote['mid']}, "
                        f"Spread: {quote['spread_pips']}."
                    ),
                )
            )

            from .multi_timeframe import MultiTimeframeService
            from .economic_calendar import EconomicCalendarService
            from .session_filter import SessionFilterService

            mtf = MultiTimeframeService.analyze_top_down(target_sym)
            is_news_blocked, news_reason, news_event = EconomicCalendarService.is_news_blocked(target_sym)
            session_info = SessionFilterService.get_current_session_info()

            atr_text = mtf["m15"].get("atr_display") or f"{mtf['m15']['atr_pips']} pips"
            plan_str = (
                f"Suggested Side: {mtf['suggested_side'].upper()}, Calculated Entry: {mtf['entry_price']}, "
                f"Stop-Loss: {mtf['stop_loss']}, Take-Profit: {mtf['take_profit']} (R:R {mtf['rr_ratio']}R)."
                if mtf.get("suggested_side") else
                f"Suggested Side: HOLD. Actionable Plan: STAND DOWN (No entry permitted due to {mtf['confluence_quality']} alignment)."
            )

            contexts.append(
                ToolContext(
                    name="top_down_institutional_confluence",
                    content=(
                        f"Top-Down Multi-Timeframe Confluence for {target_sym}: "
                        f"4H Macro Bias: {mtf['macro_bias_4h']} (RSI: {mtf['h4']['rsi']}, EMA200: {mtf['h4']['ema200']}). "
                        f"1H Structure: {mtf['h1']['direction'].upper()} (RSI: {mtf['h1']['rsi']}). "
                        f"15M Trigger: {mtf['m15']['direction'].upper()} (RSI: {mtf['m15']['rsi']}, ATR: {atr_text}). "
                        f"Alignment Status: {mtf['confluence_quality']} (Composite Score: {mtf['composite_score']}/100, Aligned: {mtf['is_aligned']}). "
                        f"Analysis Note: {mtf.get('rejection_reason') or 'Institutional multi-timeframe alignment confirmed'}. "
                        f"{plan_str}"
                    ),
                )
            )

            contexts.append(
                ToolContext(
                    name="economic_news_shield",
                    content=(
                        f"High-Impact News Shield: {'BLOCKED (High Risk)' if is_news_blocked else 'CLEAR (Safe to Trade)'}. "
                        f"Details: {news_reason}."
                    ),
                )
            )

            contexts.append(
                ToolContext(
                    name="session_liquidity_clock",
                    content=(
                        f"Global Trading Session: {session_info['primary_session']} "
                        f"(Active: {', '.join(session_info.get('active_sessions', []))}). "
                        f"Liquidity Rating: {session_info['liquidity_rating']}. "
                        f"Session Note: {session_info.get('advice') or session_info.get('note', '')}. "
                        f"Rollover Spread Warning: {session_info['is_rollover']}."
                    ),
                )
            )

        except Exception as exc:
            contexts.append(ToolContext(name="market_status", content=f"Market analysis for {target_sym} unavailable: {exc}"))

    # Opportunity scanner for general queries about what to trade
    scan_kws = (
        "other pair", "which pair", "what can we trade", "what else", "any setup",
        "promising to trade", "any pair", "what crypto", "what forex", "any gold",
        "best pair", "best trade", "scan all", "scan pairs", "scan the market",
    )
    if any(k in message for k in scan_kws):
        from .multi_timeframe import MultiTimeframeService
        scan_pairs = ["EUR/USD", "GBP/USD", "XAU/USD", "BTC/USD", "ETH/USD"]
        scan_results = []
        for p in scan_pairs:
            try:
                p_mtf = MultiTimeframeService.analyze_top_down(p)
                entry_str = f", Entry: {p_mtf['entry_price']}" if p_mtf.get('entry_price') else ""
                sl_str = f", SL: {p_mtf['stop_loss']}" if p_mtf.get('stop_loss') else ""
                tp_str = f", TP: {p_mtf['take_profit']}" if p_mtf.get('take_profit') else ""
                scan_results.append(
                    f"- {p}: 4H {p_mtf['macro_bias_4h']} | Alignment: {p_mtf['confluence_quality']} "
                    f"({p_mtf['composite_score']}/100) | Side: {(p_mtf['suggested_side'] or 'HOLD').upper()}"
                    f"{entry_str}{sl_str}{tp_str}"
                )
            except Exception:
                pass
        if scan_results:
            contexts.append(
                ToolContext(
                    name="market_scanner_overview",
                    content=(
                        "Multi-Pair Opportunity Scanner (Exness MT5 Active Instruments — Forex + Gold + Crypto):\n"
                        + "\n".join(scan_results)
                        + "\n\nBroker Note: EUR/USD, GBP/USD, XAU/USD, BTC/USD, ETH/USD are actively tradable 24/7 on this Exness MT5 Demo server. SOL, XRP, LTC have weekend broker restrictions (trade_mode=0)."
                    ),
                )
            )

    # 3. Backtest Context
    if backtest_id:
        run = (
            BacktestRun.objects.filter(id=backtest_id, owner=user)
            .select_related("agent")
            .prefetch_related("trades")
            .first()
        )
        if run:
            backtest_payload = serialize_backtest(run)
            contexts.extend(_saved_backtest_contexts(backtest_payload))

    return contexts


def _generate_reply(thread: ChatThread, user_message: str, contexts: list[ToolContext]) -> str:
    history = "\n".join(
        f"{message.role.upper()}: {message.content}"
        for message in thread.messages.order_by("-created_at")[:8]
    )
    tool_context = "\n".join(f"{context.name}: {context.content}" for context in contexts) or "No tool data needed."
    system_prompt = _system_prompt_for_contexts(contexts)

    if settings.GEMINI_API_KEY and genai is not None:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            prompt = (
                f"{system_prompt}\n\n"
                f"Current UTC time: {timezone.now().isoformat()}\n"
                f"Recent conversation:\n{history}\n\n"
                f"Live Tool & Market Context:\n{tool_context}\n\n"
                f"User Request: {user_message}"
            )

            preferred_model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
            candidate_models = [
                preferred_model,
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-3.5-flash",
                "gemini-3.8-flash",
                "gemini-3.7-flash",
                "gemini-3.5-flash-lite",
                "gemini-3.1-flash-lite",
            ]
            models_to_try = []
            for m in candidate_models:
                if m and m not in models_to_try:
                    models_to_try.append(m)

            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(model=model_name, contents=prompt)
                    text = getattr(response, "text", None)
                    if text and text.strip():
                        logger.info(f"Generated TradeFlow AI reply using model: {model_name}")
                        return text.strip()
                except Exception as model_err:
                    logger.warning(f"Gemini model {model_name} failed: {model_err}. Falling back to next...")

        except Exception as exc:
            logger.warning("Gemini client initialization failed; using research synthesis.", exc_info=exc)

    return _fallback_reply(contexts, user_message)


def _fallback_reply(contexts: list[ToolContext], user_message: str) -> str:
    order_exec = next((c.content for c in contexts if c.name == "order_execution_result"), None)
    if order_exec:
        return f"### Order Execution Update\n\n{order_exec}"

    quote_ctx = next((c.content for c in contexts if c.name == "forex_market_quote"), None)
    mtf_ctx = next((c.content for c in contexts if c.name == "top_down_institutional_confluence"), None)
    news_ctx = next((c.content for c in contexts if c.name == "economic_news_shield"), None)
    session_ctx = next((c.content for c in contexts if c.name == "session_liquidity_clock"), None)
    broker_ctx = next((c.content for c in contexts if c.name == "active_broker_and_account"), None)

    if mtf_ctx:
        return (
            f"### TradeFlow Institutional Analysis\n\n"
            f"**Market Context:** {quote_ctx or 'Live market quote active'}\n"
            f"**Session & Liquidity:** {session_ctx or 'Standard session liquidity'}\n\n"
            f"**Top-Down Confluence:**\n{mtf_ctx}\n\n"
            f"**Economic Calendar Guardrail:**\n{news_ctx or 'News Shield Clear'}\n\n"
            f"**Actionable Execution:**\n"
            f"To automatically execute this trade on your active broker ({broker_ctx or 'MT5 Demo'}), simply reply: **'execute trade'** or **'buy 0.01 lot EUR/USD'**."
        )

    account = next((c.content for c in contexts if c.name == "active_broker_and_account"), None)
    if account:
        return f"### Account & Risk Overview\n\n{account}"

    return "I analyzed your request against live market data and risk rules. Let me know which currency pair you'd like to inspect or trade!"


def _system_prompt_for_contexts(contexts: list[ToolContext]) -> str:
    return (
        "You are TradeFlow AI, an institutional-grade algorithmic trading copilot connected directly to "
        "MetaTrader 5 (Exness Demo Account) and Alpaca Paper Trading. "
        "You operate with the precision, rigor, and discipline of an elite institutional portfolio manager.\n\n"
        "CAPABILITIES & BROKER ROUTING:\n"
        "1. Spot Forex (EUR/USD, GBP/USD, USD/JPY, etc.) and 24/7 Crypto (BTC/USD, ETH/USD, XRP/USD, LTC/USD, SOL/USD, etc.) are routed directly to MetaTrader 5 (Exness) supporting 0.01 micro-lot sizing and ultra-tight spreads.\n"
        "2. US Equities are routed to Alpaca Paper Trading.\n"
        "3. You can AUTOMATICALLY EXECUTE trades directly when instructed by the user in the chat interface (e.g., 'buy 0.01 lot EUR/USD', 'buy 0.01 ETH/USD', 'execute trade', 'close BTC/USD').\n\n"
        "INSTITUTIONAL ANALYSIS FRAMEWORK:\n"
        "When analyzing any currency or crypto pair for a potential trade:\n"
        "- Synthesize the live market data cleanly in professional Markdown (do NOT dump raw JSON or repeat tool prefixes).\n"
        "- Present 4 clear, well-structured sections:\n"
        "  1. **Market Snapshot & Session**: Bid/Ask, Spread, and active global liquidity session.\n"
        "  2. **Top-Down Confluence (4H -> 1H -> 15M)**: State the 4H macro bias, 1H structure, and 15M trigger. Explicitly explain whether there is institutional alignment or a counter-trend trap.\n"
        "  3. **Institutional Guardrails**: Status of High-Impact Red-Folder Economic News Shield and Session Rollover spread risk.\n"
        "  4. **Actionable Trading Plan**: Clear YES or NO verdict on entering. If entering, specify Recommended Side (BUY/SELL), Entry Price, Protective Stop-Loss (strictly below entry for Buy, above for Sell), Take-Profit (minimum 1.5R - 2.0R), and Position Sizing (e.g. 0.01 lot).\n"
        "- Conclude with a clear instruction on how to execute: e.g. 'To execute this trade immediately on your Exness MT5 demo account, simply type: **\"execute trade\"** or **\"buy 0.01 ETH/USD\"**.'\n\n"
        "If an order execution was just performed (see order_execution_result context):\n"
        "- Announce the successful trade execution clearly with Ticket Number, Broker (Exness MT5), Fill Price, SL, and TP.\n"
        "- Confirm that position protection and risk guardrails are active.\n"
        "Always be concise, authoritative, and focused on capital preservation."
    )




def _saved_backtest_contexts(backtest: dict[str, Any]) -> list[ToolContext]:
    metrics = backtest["metrics"]
    return [
        ToolContext(
            name="saved_backtest_summary",
            content=(
                f"Saved backtest for {backtest['symbol']} ({backtest['timeframe']}): "
                f"Return: {metrics['totalReturnPct']:.2f}%, Sharpe: {metrics['sharpeRatio']:.2f}, "
                f"Drawdown: {metrics['maxDrawdownPct']:.2f}%, Win Rate: {metrics['winRate']:.2f}%, "
                f"Total Trades: {metrics['totalTrades']}."
            ),
        )
    ]
