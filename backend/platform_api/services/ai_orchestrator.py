from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.conf import settings
from django.utils import timezone

try:
    from google import genai
except ImportError:  # pragma: no cover - dependency is optional during editing
    genai = None

from ..defaults import DEFAULT_AGENT
from ..models import Agent, BacktestRun, ChatMessage, ChatThread, UsageEvent
from ..presenters import serialize_backtest, serialize_chat_message
from .backtests import run_backtest
from .market_data import get_candles, latest_price

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    name: str
    content: str


def handle_chat(user, payload: dict[str, Any]) -> dict[str, Any]:
    thread = _resolve_thread(user, payload)
    ChatMessage.objects.create(thread=thread, role="user", content=payload["message"])

    contexts = _collect_contexts(user, payload)
    for context in contexts:
        ChatMessage.objects.create(
            thread=thread,
            role="tool",
            content=context.content,
            metadata={"tool": context.name},
        )

    reply = _generate_reply(thread, payload["message"], contexts)
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
            contexts.extend(_saved_backtest_focus_contexts(backtest_payload, payload))
            symbol = symbol or backtest_payload["symbol"]
            timeframe = timeframe or backtest_payload["timeframe"]
        else:
            contexts.append(
                ToolContext(
                    name="saved_backtest_status",
                    content=f"The requested saved backtest {backtest_id} was not found for this account.",
                )
            )

    if symbol or any(keyword in message for keyword in ("market", "price", "chart", "candle", "btc", "eth")):
        symbol = symbol or "BTCUSDT"
        try:
            candles = get_candles(symbol, timeframe, limit=50)
            last_price = latest_price(symbol, timeframe)
            change_pct = 0.0
            if len(candles) > 1:
                previous_close = candles[-2]["close"]
                if previous_close:
                    change_pct = ((last_price - previous_close) / previous_close) * 100
            contexts.append(
                ToolContext(
                    name="market_data",
                    content=f"Market data for {symbol} ({timeframe}): last price {last_price:.2f}, 1-bar change {change_pct:.2f}%, candles loaded {len(candles)}.",
                )
            )
        except ValueError as exc:
            contexts.append(
                ToolContext(
                    name="market_data_status",
                    content=f"Live market data for {symbol} ({timeframe}) is currently unavailable: {exc}",
                )
            )

    if not backtest_id and any(keyword in message for keyword in ("backtest", "strategy", "agent", "model", "signal", "probability", "prediction")):
        symbol = symbol or "BTCUSDT"
        agent = Agent.objects.filter(owner=user, id=payload.get("agentId")).first() if payload.get("agentId") else None
        agent_payload = {
            "id": str(agent.id) if agent else None,
            "name": agent.name if agent else DEFAULT_AGENT["name"],
            "type": agent.type if agent else DEFAULT_AGENT["type"],
            "rewardStyle": agent.reward_style if agent else DEFAULT_AGENT["rewardStyle"],
            "riskTolerance": agent.risk_tolerance if agent else DEFAULT_AGENT["riskTolerance"],
            "holdingBehavior": agent.holding_behavior if agent else DEFAULT_AGENT["holdingBehavior"],
            "strategies": agent.strategies if agent else DEFAULT_AGENT["strategies"],
        }
        try:
            candles = get_candles(symbol, timeframe, limit=300)
            result = run_backtest(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "agent": agent_payload,
                    "settings": {
                        "startingBalance": 10000,
                        "feeRate": 0.001,
                        "slippageRate": 0.0005,
                        "positionSizeFraction": 0.95,
                    },
                },
                candles,
            )
            metrics = result["metrics"]
            contexts.append(
                ToolContext(
                    name="backtest",
                    content=(
                        f"Backtest summary for {symbol} ({timeframe}) using {agent_payload['name']}: "
                        f"return {metrics['totalReturnPct']:.2f}%, drawdown {metrics['maxDrawdownPct']:.2f}%, "
                        f"Sharpe {metrics['sharpeRatio']:.2f}, win rate {metrics['winRate']:.2f}%, total trades {metrics['totalTrades']}."
                    ),
                )
            )
            model_analysis = result.get("modelAnalysis")
            if model_analysis:
                signal = model_analysis["signal"]
                performance = model_analysis["performance"]
                explanation = model_analysis["explanation"]
                tuning = model_analysis.get("tuning", {})
                selected_config = tuning.get("selectedConfig", {})
                contexts.append(
                    ToolContext(
                        name="model_analysis",
                        content=(
                            f"Model analysis for {symbol} ({timeframe}): action {signal['action']}, "
                            f"upside probability {signal['probabilityUpPct']:.2f}%, confidence {signal['confidencePct']:.2f}%, "
                            f"held-out accuracy {performance['testAccuracyPct']:.2f}%, precision {performance['testPrecisionPct']:.2f}%, "
                            f"tuned horizon {selected_config.get('horizonBars', 0)} bars, learning rate {selected_config.get('learningRate', 0):.2f}, "
                            f"regularization {selected_config.get('regularization', 0):.4f}. "
                            f"Summary: {explanation['summary']}"
                        ),
                    )
                )
        except ValueError as exc:
            contexts.append(
                ToolContext(
                    name="backtest_status",
                    content=f"Fresh backtest context for {symbol} ({timeframe}) could not be generated: {exc}",
                )
            )

    return contexts


def _generate_reply(thread: ChatThread, user_message: str, contexts: list[ToolContext]) -> str:
    history = "\n".join(
        f"{message.role.upper()}: {message.content}"
        for message in thread.messages.order_by("-created_at")[:10]
    )
    tool_context = "\n".join(f"{context.name}: {context.content}" for context in contexts) or "No tool data was needed."
    system_prompt = _system_prompt_for_contexts(contexts)

    if settings.GEMINI_API_KEY and genai is not None:
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            prompt = (
                f"{system_prompt}\n\n"
                f"Current UTC time: {timezone.now().isoformat()}\n"
                f"Recent conversation:\n{history}\n\n"
                f"Tool results:\n{tool_context}\n\n"
                f"User request: {user_message}"
            )
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            text = getattr(response, "text", None)
            if text:
                return text
        except Exception as exc:  # pragma: no cover - provider-specific failure paths vary
            logger.warning("Gemini reply generation failed; falling back to backend summary.", exc_info=exc)
            return _fallback_reply(
                contexts,
                "Gemini is unavailable right now, so I used the backend research context instead.",
            )

    return _fallback_reply(contexts)


def _fallback_reply(contexts: list[ToolContext], prefix: str | None = None) -> str:
    base = prefix.strip() if prefix else ""
    focused_brief = next((context.content for context in contexts if context.name == "focused_replay_brief"), None)
    if focused_brief:
        if base:
            return f"{base} {focused_brief} Let me know if you want the same treatment for the next trade, the current replay bar, or the whole run."
        return f"{focused_brief} Let me know if you want the same treatment for the next trade, the current replay bar, or the whole run."
    backtest_brief = next((context.content for context in contexts if context.name == "backtest_operator_brief"), None)
    if backtest_brief:
        if base:
            return f"{base} {backtest_brief} Let me know if you want a sharper critique of the strategy rules, the model signal, or the next parameters to test."
        return f"{backtest_brief} Let me know if you want a sharper critique of the strategy rules, the model signal, or the next parameters to test."
    if contexts:
        joined = " ".join(context.content for context in contexts)
        if base:
            return f"{base} I reviewed the latest backend tool results. {joined} Let me know if you want a saved backtest run or a deeper agent comparison."
        return f"I reviewed the latest backend tool results. {joined} Let me know if you want a saved backtest run or a deeper agent comparison."
    if base:
        return f"{base} I can help analyze the market, compare strategy templates, or summarize a backtest. Add a symbol like BTCUSDT and I'll work from there."
    return "I can help analyze the market, compare strategy templates, or summarize a backtest. Add a symbol like BTCUSDT and I'll work from there."


def _system_prompt_for_contexts(contexts: list[ToolContext]) -> str:
    has_replay_focus = any(context.name in {"saved_backtest_trade_focus", "saved_backtest_replay_focus"} for context in contexts)
    if has_replay_focus:
        return (
            "You are TradeFlow AI, a disciplined trading research copilot explaining one specific replay decision. "
            "Answer the operator's direct question first: why this trade happened here, or what the strategy knew at this replay moment. "
            "Use a compact format: Why here, What the strategy knew, and What to test next if helpful. "
            "Stay grounded in the saved trade log, replay focus, enabled strategy rules, and run statistics. "
            "If exact candle-by-candle evidence is unavailable from the saved run, say so plainly and explain what is still knowable from the rule stack and the revealed trades. "
            "Avoid hype, filler, and generic coaching language."
        )

    has_saved_backtest = any(context.name.startswith("saved_backtest") for context in contexts)
    if has_saved_backtest:
        return (
            "You are TradeFlow AI, a disciplined trading research copilot focused on backtest review. "
            "Respond like a serious operator reviewing one specific run, not like a generic chatbot. "
            "Lead with the verdict in plain English. If the strategy underperformed the benchmark or failed walk-forward validation, say that clearly before discussing any positive metrics. "
            "When model quality looks stronger than strategy quality, explain the mismatch directly: a short-horizon predictive model can look good while the full trading rule set still performs poorly. "
            "Use a compact operator brief format: Verdict, Why it happened, and Next tests. "
            "Keep each section short. Avoid markdown-heavy templates like 'What Failed' or 'What Passed', avoid hype, avoid filler, and avoid mentioning tools unless necessary. "
            "Be concrete, practical, and grounded in the provided run statistics."
        )

    return (
        "You are TradeFlow AI, a disciplined crypto strategy research assistant. "
        "Give concise, practical answers, avoid hype, and ground recommendations in the provided tool results."
    )


def _guess_symbol_from_text(message: str) -> str | None:
    for token in message.upper().replace("/", " ").split():
        if token.endswith("USDT") and len(token) >= 6:
            return token
    return None


def _saved_backtest_contexts(backtest: dict[str, Any]) -> list[ToolContext]:
    metrics = backtest["metrics"]
    walk_forward = backtest.get("walkForward") or {}
    model_analysis = backtest.get("modelAnalysis") or {}
    enabled_strategies = [strategy["name"] for strategy in backtest["agent"]["strategies"] if strategy.get("enabled")]

    contexts = [
        ToolContext(
            name="saved_backtest_summary",
            content=(
                f"Saved backtest for {backtest['symbol']} ({backtest['timeframe']}) run at {backtest['createdAt']}: "
                f"return {metrics['totalReturnPct']:.2f}%, benchmark {metrics['benchmarkReturnPct']:.2f}%, "
                f"excess return {metrics['excessReturnPct']:.2f}%, Sharpe {metrics['sharpeRatio']:.2f}, "
                f"drawdown {metrics['maxDrawdownPct']:.2f}%, win rate {metrics['winRate']:.2f}%, "
                f"closed trades {metrics['totalTrades']}, exposure {metrics['exposureTimePct']:.2f}%."
            ),
        ),
        ToolContext(
            name="saved_backtest_rules",
            content=(
                f"Enabled strategies for this run: {', '.join(enabled_strategies) if enabled_strategies else 'none'}. "
                f"Validation warnings: {', '.join(backtest['validation']['warnings']) if backtest['validation']['warnings'] else 'none'}."
            ),
        ),
    ]

    if walk_forward:
        contexts.append(
            ToolContext(
                name="saved_backtest_walk_forward",
                content=(
                    f"Walk-forward verdict {walk_forward.get('verdict', 'unavailable')}, average test return {walk_forward.get('averageTestReturnPct', 0):.2f}%, "
                    f"average test excess {walk_forward.get('averageTestExcessReturnPct', 0):.2f}%, "
                    f"benchmark beat rate {walk_forward.get('benchmarkBeatRatePct', 0):.2f}%, "
                    f"profitable window rate {walk_forward.get('profitableWindowPct', 0):.2f}% across {walk_forward.get('windowCount', 0)} windows."
                ),
            )
        )

    if model_analysis:
        signal = model_analysis.get("signal", {})
        performance = model_analysis.get("performance", {})
        tuning = model_analysis.get("tuning", {})
        selected_config = tuning.get("selectedConfig", {})
        contexts.append(
            ToolContext(
                name="saved_backtest_model",
                content=(
                    f"Model signal for this run: {signal.get('action', 'hold')} with upside probability {signal.get('probabilityUpPct', 50):.2f}%, "
                    f"confidence {signal.get('confidencePct', 0):.2f}%, held-out accuracy {performance.get('testAccuracyPct', 0):.2f}%, "
                    f"long hit rate {performance.get('predictedLongHitRatePct', 0):.2f}%, tuned horizon {selected_config.get('horizonBars', 0)} bars."
                ),
            )
        )
        contexts.append(ToolContext(name="backtest_operator_brief", content=_build_backtest_operator_brief(backtest)))

    return contexts


def _saved_backtest_focus_contexts(backtest: dict[str, Any], payload: dict[str, Any]) -> list[ToolContext]:
    trades = backtest.get("trades") or []
    if not trades:
        return []

    contexts: list[ToolContext] = []
    replay_at = _coerce_datetime(payload.get("replayTime"))
    playback_index = payload.get("playbackIndex")
    selected_trade = next((trade for trade in trades if trade["id"] == str(payload.get("tradeId"))), None)

    revealed_trades: list[dict[str, Any]] = []
    latest_revealed: dict[str, Any] | None = None
    next_hidden_trade: dict[str, Any] | None = None
    if replay_at is not None:
        for trade in trades:
            trade_time = _coerce_datetime(trade.get("time"))
            if trade_time is None:
                continue
            if trade_time <= replay_at:
                revealed_trades.append(trade)
            elif next_hidden_trade is None:
                next_hidden_trade = trade
        latest_revealed = revealed_trades[-1] if revealed_trades else None
        contexts.append(
            ToolContext(
                name="saved_backtest_replay_focus",
                content=(
                    f"Replay focus at {replay_at.isoformat()}"
                    f"{f' on replay bar {playback_index}' if playback_index is not None else ''}: "
                    f"{len(revealed_trades)} trade events were already revealed. "
                    f"Latest revealed trade: {_format_trade_summary(latest_revealed) if latest_revealed else 'none yet'}. "
                    f"Next hidden trade after this moment: {_format_trade_summary(next_hidden_trade) if next_hidden_trade else 'none; this is near the end of the run'}."
                ),
            )
        )

    if selected_trade is not None:
        selected_index = trades.index(selected_trade)
        previous_trade = trades[selected_index - 1] if selected_index > 0 else None
        next_trade = trades[selected_index + 1] if selected_index + 1 < len(trades) else None
        paired_trade = _find_paired_trade(trades, selected_index)
        contexts.append(
            ToolContext(
                name="saved_backtest_trade_focus",
                content=(
                    f"Selected trade: {_format_trade_summary(selected_trade)}. "
                    f"Previous trade in the run: {_format_trade_summary(previous_trade) if previous_trade else 'none'}. "
                    f"Next trade in the run: {_format_trade_summary(next_trade) if next_trade else 'none'}. "
                    f"Closest paired round-trip outcome: {_format_trade_outcome(selected_trade, paired_trade)}."
                ),
            )
        )
        contexts.append(
            ToolContext(
                name="focused_replay_brief",
                content=_build_trade_focus_brief(backtest, selected_trade, paired_trade, latest_revealed),
            )
        )
        return contexts

    if replay_at is not None:
        contexts.append(
            ToolContext(
                name="focused_replay_brief",
                content=_build_replay_focus_brief(backtest, replay_at, playback_index, latest_revealed, next_hidden_trade, len(revealed_trades)),
            )
        )

    return contexts


def _build_backtest_operator_brief(backtest: dict[str, Any]) -> str:
    metrics = backtest["metrics"]
    walk_forward = backtest.get("walkForward") or {}
    model_analysis = backtest.get("modelAnalysis") or {}
    enabled_strategies = [strategy["name"] for strategy in backtest["agent"]["strategies"] if strategy.get("enabled")]

    lines = []
    if metrics["excessReturnPct"] < 0:
        lines.append(
            f"This run is not strong enough yet: the strategy made {metrics['totalReturnPct']:.2f}% while buy-and-hold made {metrics['benchmarkReturnPct']:.2f}%, so it lagged by {abs(metrics['excessReturnPct']):.2f} percentage points."
        )
    else:
        lines.append(
            f"This run beat buy-and-hold by {metrics['excessReturnPct']:.2f} percentage points, which is the first sign of real edge."
        )

    if walk_forward.get("available"):
        if walk_forward.get("verdict") == "fail":
            lines.append(
                f"The bigger problem is robustness: the walk-forward test failed, with average out-of-sample excess return {walk_forward.get('averageTestExcessReturnPct', 0):.2f}% and a benchmark beat rate of {walk_forward.get('benchmarkBeatRatePct', 0):.2f}%."
            )
        elif walk_forward.get("verdict") == "mixed":
            lines.append(
                f"The walk-forward result is mixed, so the edge is not stable yet. Average out-of-sample excess return was {walk_forward.get('averageTestExcessReturnPct', 0):.2f}%."
            )
        else:
            lines.append(
                f"The walk-forward result is encouraging, which means the strategy held up better on unseen windows than it did in a single in-sample run."
            )

    if model_analysis.get("available"):
        signal = model_analysis["signal"]
        performance = model_analysis["performance"]
        lines.append(
            f"The BUY model signal is a short-horizon forecast for the next {model_analysis.get('labelHorizonBars', 0)} bars, not proof that the whole strategy is good. That is why you can see BUY with {signal.get('probabilityUpPct', 50):.2f}% upside probability and still have a weak overall strategy if the rule set misses most of the broader move."
        )
        lines.append(
            f"The model itself looks statistically cleaner than the strategy rules right now, with held-out accuracy {performance.get('testAccuracyPct', 0):.2f}% and long hit rate {performance.get('predictedLongHitRatePct', 0):.2f}%."
        )

    if enabled_strategies:
        lines.append(
            f"The active rule stack on this run was {', '.join(enabled_strategies)}. The next job is to change or retune the rule logic until the full strategy starts beating buy-and-hold and survives walk-forward validation."
        )

    return " ".join(lines)


def _build_trade_focus_brief(
    backtest: dict[str, Any],
    selected_trade: dict[str, Any],
    paired_trade: dict[str, Any] | None,
    latest_revealed: dict[str, Any] | None,
) -> str:
    enabled_strategies = [strategy["name"] for strategy in backtest["agent"]["strategies"] if strategy.get("enabled")]
    lines = [
        f"This {selected_trade['type'].upper()} happened here because the active rule stack flagged an entry or exit and recorded the reason as: {selected_trade['reason']}",
    ]
    if paired_trade:
        lines.append(
            f"In the saved run, the closest paired trade was {_format_trade_summary(paired_trade)}, which means this decision eventually translated into {_format_trade_outcome(selected_trade, paired_trade)}."
        )
    if latest_revealed and latest_revealed["id"] != selected_trade["id"]:
        lines.append(
            f"At the replay moment around this trade, the latest already-revealed action was {_format_trade_summary(latest_revealed)}, so this decision was part of an ongoing sequence rather than a standalone signal."
        )
    lines.append(
        f"The rule stack on this run was {', '.join(enabled_strategies) if enabled_strategies else 'no enabled rules'}, so the cleanest next step is to check whether those rules are entering too late, exiting too early, or reacting to noise."
    )
    lines.append(
        "Because this explanation comes from the saved run and trade log, treat it as a timing-and-rule explanation rather than a full candle-forensics reconstruction."
    )
    return " ".join(lines)


def _build_replay_focus_brief(
    backtest: dict[str, Any],
    replay_at: datetime,
    playback_index: int | None,
    latest_revealed: dict[str, Any] | None,
    next_hidden_trade: dict[str, Any] | None,
    revealed_count: int,
) -> str:
    metrics = backtest["metrics"]
    enabled_strategies = [strategy["name"] for strategy in backtest["agent"]["strategies"] if strategy.get("enabled")]
    lines = [
        (
            f"At replay time {replay_at.isoformat()}"
            f"{f' on bar {playback_index}' if playback_index is not None else ''}, the strategy had already revealed {revealed_count} trade events."
        )
    ]
    if latest_revealed:
        lines.append(f"The latest visible action was {_format_trade_summary(latest_revealed)}.")
    else:
        lines.append("No trade had fired yet at this replay point, so the strategy was still waiting for its first qualified setup.")
    if next_hidden_trade:
        lines.append(f"The next hidden action after this moment was {_format_trade_summary(next_hidden_trade)}, which hints at what the rule stack was close to doing next.")
    lines.append(
        f"The active rule stack was {', '.join(enabled_strategies) if enabled_strategies else 'no enabled rules'}, and the finished run ended with {metrics['totalReturnPct']:.2f}% return versus {metrics['benchmarkReturnPct']:.2f}% for buy-and-hold."
    )
    return " ".join(lines)


def _find_paired_trade(trades: list[dict[str, Any]], selected_index: int) -> dict[str, Any] | None:
    selected_trade = trades[selected_index]
    if selected_trade["type"] == "buy":
        return next((trade for trade in trades[selected_index + 1 :] if trade["type"] == "sell"), None)
    return next((trade for trade in reversed(trades[:selected_index]) if trade["type"] == "buy"), None)


def _format_trade_outcome(selected_trade: dict[str, Any], paired_trade: dict[str, Any] | None) -> str:
    if paired_trade is None:
        return "no completed paired outcome yet"

    if selected_trade["type"] == "buy":
        move = paired_trade["price"] - selected_trade["price"]
        pct_move = (move / selected_trade["price"]) * 100 if selected_trade["price"] else 0
        direction = "gain" if move >= 0 else "loss"
        return f"a {direction} of {move:.2f} points ({pct_move:.2f}%) by the time the paired exit arrived"

    move = selected_trade["price"] - paired_trade["price"]
    pct_move = (move / paired_trade["price"]) * 100 if paired_trade["price"] else 0
    direction = "gain" if move >= 0 else "loss"
    return f"a {direction} of {move:.2f} points ({pct_move:.2f}%) from the prior entry into this exit"


def _format_trade_summary(trade: dict[str, Any] | None) -> str:
    if trade is None:
        return "none"
    return f"{trade['type'].upper()} at {trade['price']:.2f} on {trade['time']} because {trade['reason']}"


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
