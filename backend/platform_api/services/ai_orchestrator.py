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

    # 1. Check for explicit trade execution intent (e.g., "buy EUR/USD", "close position")
    execution_result = _handle_trade_intents(user, thread.agent, user_msg)
    if execution_result:
        ChatMessage.objects.create(
            thread=thread,
            role="tool",
            content=execution_result["summary"],
            metadata={"tool": "order_execution", "result": execution_result},
        )

    # 2. Collect rich market, technical, risk, and account contexts
    contexts = _collect_contexts(user, payload)
    if execution_result:
        contexts.insert(0, ToolContext(name="order_execution_result", content=execution_result["summary"]))

    for context in contexts:
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


def _handle_trade_intents(user, agent: Optional[Agent], message: str) -> Optional[dict[str, Any]]:
    """
    Parses natural language execution commands like:
    - 'buy 1000 EUR/USD'
    - 'sell 500 GBP/USD with sl 1.2850'
    - 'close EUR/USD position'
    - 'close all positions'
    """
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
        res = OrderExecutionService.close_position(target_sym)
        if res.get("success"):
            return {
                "action": "close_position",
                "summary": f"Successfully closed position for {target_sym} at {res.get('closed_at_price')}.",
            }
        return {"action": "close_position", "summary": f"Could not close position for {target_sym}: {res.get('error')}"}

    # Order execution intent: buy or sell
    trade_match = re.search(r"\b(buy|sell|long|short)\b\s+([\d,.]+)?\s*([a-zA-Z]{1,6}(?:/[a-zA-Z]{3})?)?", msg)
    if trade_match and any(term in msg for term in ("execute", "place", "order", "enter", "trade", "buy", "sell")):
        raw_side = trade_match.group(1).lower()
        side = "buy" if raw_side in ("buy", "long") else "sell"
        raw_qty = trade_match.group(2)
        qty = float(raw_qty.replace(",", "")) if raw_qty else 1000.0

        raw_sym = trade_match.group(3) or _guess_symbol_from_text(message)
        if not raw_sym:
            return None

        disp_sym = format_display_symbol(raw_sym)
        curr_px = latest_price(disp_sym)

        # Parse optional explicit SL / TP from prompt
        sl_match = re.search(r"(?:sl|stop\s*loss)[:\s]+([\d.]+)", msg)
        tp_match = re.search(r"(?:tp|take\s*profit)[:\s]+([\d.]+)", msg)

        sl = float(sl_match.group(1)) if sl_match else None
        tp = float(tp_match.group(1)) if tp_match else None

        # If not provided, dynamically compute healthy ATR brackets
        if not sl:
            confluence = analyze_forex_confluence(disp_sym)
            sl = confluence.get("stop_loss")
            tp = tp or confluence.get("take_profit")

        res = OrderExecutionService.execute_order(
            symbol=disp_sym,
            side=side,
            qty=qty,
            stop_loss=sl,
            take_profit=tp,
            agent=agent,
            ai_reasoning=f"Chat execution requested by user: '{message}'",
        )

        if res.get("success"):
            return {
                "action": "execute_order",
                "summary": (
                    f"Successfully placed {side.upper()} order for {qty} units of {disp_sym} on Alpaca "
                    f"at ~{res.get('entry_price')}. Attached Stop-Loss: {sl}, Take-Profit: {tp}. Order ID: {res.get('order_id')}."
                ),
                "details": res,
            }
        else:
            return {
                "action": "execute_order_rejected",
                "summary": f"Order could not be placed due to risk rule violation: {res.get('error')}",
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


def _collect_contexts(user, payload: dict[str, Any]) -> list[ToolContext]:
    message = payload["message"].lower()
    contexts: list[ToolContext] = []
    symbol = payload.get("symbol") or _guess_symbol_from_text(payload["message"])
    timeframe = payload.get("timeframe") or "1h"
    backtest_id = payload.get("backtestId")

    # 1. Live Alpaca Account & Risk Guardrails Context
    try:
        acc = OrderExecutionService.get_account_overview()
        rules = RiskManager.get_all_rules()
        positions = OrderExecutionService.get_open_positions()
        contexts.append(
            ToolContext(
                name="alpaca_account_and_risk",
                content=(
                    f"Alpaca Account ({acc['mode'].upper()} mode, status: {acc['status']}): "
                    f"Equity: ${acc['equity']:,.2f}, Cash: ${acc['cash']:,.2f}, Buying Power: ${acc['buying_power']:,.2f}. "
                    f"Open positions count: {len(positions)}. "
                    f"Enforced Risk Rules: Max Risk/Trade: {rules.get('max_risk_pct')}%, "
                    f"Daily Loss Limit: {rules.get('daily_loss_limit_pct')}%, "
                    f"Min R:R: {rules.get('min_rr_ratio')}R, Mandatory Stop-Loss: {rules.get('require_stop_loss')}."
                ),
            )
        )
        if positions:
            pos_summary = ", ".join(
                f"{p['symbol']} ({p['side']} {p['qty']}, entry {p['avg_entry_price']}, unrealized PnL: ${p['unrealized_pnl']:.2f})"
                for p in positions[:4]
            )
            contexts.append(ToolContext(name="open_positions", content=f"Current open positions: {pos_summary}"))
    except Exception as exc:
        logger.warning(f"Could not gather account context: {exc}")

    # 2. Forex Market Data & Technical Confluence Context
    if symbol or any(kw in message for kw in ("forex", "eur", "gbp", "jpy", "usd", "market", "price", "signal", "pair")):
        target_sym = symbol or "EUR/USD"
        try:
            quote = get_forex_quote(target_sym)
            confluence = analyze_forex_confluence(target_sym, timeframe=timeframe)
            contexts.append(
                ToolContext(
                    name="forex_market_quote",
                    content=(
                        f"Live Quote for {quote['symbol']}: Bid: {quote['bid']}, Ask: {quote['ask']}, Mid: {quote['mid']}, "
                        f"Spread: {quote['spread_pips']} pips."
                    ),
                )
            )
            contexts.append(
                ToolContext(
                    name="technical_confluence",
                    content=(
                        f"Multi-Indicator Confluence for {target_sym} ({timeframe}): "
                        f"Signal Direction: {confluence['direction'].upper()}, Confidence: {confluence['confidence_pct']}%, "
                        f"Suggested Side: {confluence['suggested_side'].upper()}. "
                        f"Calculated Stop-Loss: {confluence['stop_loss']}, Take-Profit: {confluence['take_profit']} (R:R {confluence['rr_ratio']}R). "
                        f"ATR: {confluence['atr_pips']} pips, RSI: {confluence['indicators']['rsi']}, "
                        f"EMA 20: {confluence['indicators']['ema20']}, EMA 50: {confluence['indicators']['ema50']}, EMA 200: {confluence['indicators']['ema200']}. "
                        f"Key Factors: {'; '.join(confluence['reasons'][:3])}"
                    ),
                )
            )
        except Exception as exc:
            contexts.append(ToolContext(name="market_status", content=f"Market analysis for {target_sym} unavailable: {exc}"))

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
                f"Tool & Market Context:\n{tool_context}\n\n"
                f"User Request: {user_message}"
            )
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            text = getattr(response, "text", None)
            if text:
                return text
        except Exception as exc:
            logger.warning("Gemini reply generation failed; using research synthesis.", exc_info=exc)

    return _fallback_reply(contexts, user_message)


def _fallback_reply(contexts: list[ToolContext], user_message: str) -> str:
    order_exec = next((c.content for c in contexts if c.name == "order_execution_result"), None)
    confluence = next((c.content for c in contexts if c.name == "technical_confluence"), None)
    account = next((c.content for c in contexts if c.name == "alpaca_account_and_risk"), None)

    parts = []
    if order_exec:
        parts.append(f"**Execution Update:** {order_exec}")
    if confluence:
        parts.append(f"**Technical Analysis:** {confluence}")
    if account and not order_exec:
        parts.append(f"**Account Status:** {account}")

    if parts:
        return "\n\n".join(parts)
    return "I analyzed your request against live Alpaca market data and risk rules. Let me know which currency pair you'd like to inspect or trade!"


def _system_prompt_for_contexts(contexts: list[ToolContext]) -> str:
    return (
        "You are TradeFlow AI, an institutional-grade algorithmic trading copilot connected directly to Alpaca Markets paper trading. "
        "You have live access to active open positions (such as equities like AAPL and crypto like BTC/USD), technical indicators, Alpaca account equity, "
        "and strict risk management guardrails. "
        "IMPORTANT RULES: "
        "1. Note that Alpaca paper trading accounts support US Equities (Stocks/ETFs like AAPL, NVDA, TSLA, SPY) and Crypto (BTC/USD), but standard paper accounts do NOT support spot forex routing (which returns 422 asset not found). "
        "2. TRADE GUARDIAN & ACTIVE TRADE MANAGEMENT: When an open position is in profit (like AAPL in profit > 70%), proactively advise the user to lock in gains using Trailing Stops or Break-Even Stops so the trade never turns into a loss! "
        "Explain that a Trailing Stop (e.g., 5% or 10%) automatically trails price higher as it rallies, locking in profits, and triggers a market exit if price pulls back by that percentage. "
        "Always ground your analysis in capital preservation, reward-to-risk ratios, and risk mitigation. "
        "Be concise, practical, and direct."
    )


def _guess_symbol_from_text(message: str) -> Optional[str]:
    # Check open positions first
    try:
        from .order_execution import OrderExecutionService
        open_pos = OrderExecutionService.get_open_positions()
        for p in open_pos:
            if p["symbol"].lower() in message.lower():
                return p["symbol"]
    except Exception:
        pass

    # Check forex pairs
    clean_msg = message.upper().replace("/", "")
    for pair in FOREX_PAIRS_SET:
        if pair in clean_msg:
            return format_display_symbol(pair)

    # Check common stock tickers
    for ticker in ("AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "SPY", "QQQ"):
        if re.search(rf"\b{ticker}\b", message.upper()):
            return ticker

    # Check slashed format like EUR/USD
    match = re.search(r"\b([A-Z]{3})/([A-Z]{3})\b", message.upper())
    if match:
        return f"{match.group(1)}/{match.group(2)}"

    return None


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
