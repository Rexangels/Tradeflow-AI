from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def _trade_value(trade: Any, field: str, default=None):
    if isinstance(trade, dict):
        return trade.get(field, default)
    return getattr(trade, field, default)


def summarize_trades(trades: Iterable[Any]) -> dict[str, Any]:
    """Summarize the full journal without treating missing outcomes as losses."""
    rows = list(trades)
    closed = [row for row in rows if _trade_value(row, "status") == "closed"]
    scored = [row for row in closed if _trade_value(row, "realized_pnl") is not None]
    pnl_rows = []
    for row in scored:
        gross = float(_trade_value(row, "realized_pnl", 0) or 0)
        fee = _trade_value(row, "fee_paid")
        fee = float(fee) if fee is not None else 0.0
        pnl_rows.append((row, gross, fee, gross - fee))

    wins = [item for item in pnl_rows if item[3] > 0]
    losses = [item for item in pnl_rows if item[3] < 0]
    breakeven = len(pnl_rows) - len(wins) - len(losses)
    gross_profit = sum(max(item[1], 0.0) for item in pnl_rows)
    gross_loss = abs(sum(min(item[1], 0.0) for item in pnl_rows))
    adjusted_profit = sum(max(item[3], 0.0) for item in pnl_rows)
    adjusted_loss = abs(sum(min(item[3], 0.0) for item in pnl_rows))
    profit_factor = adjusted_profit / adjusted_loss if adjusted_loss else None

    chronological = sorted(
        pnl_rows,
        key=lambda item: _trade_value(item[0], "closed_at")
        or _trade_value(item[0], "created_at"),
    )
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for _row, _gross, _fee, net in chronological:
        equity += net
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    fees_known = sum(1 for row in scored if _trade_value(row, "fee_paid") is not None)
    pnl_sources: dict[str, int] = defaultdict(int)
    for row in scored:
        pnl_sources[str(_trade_value(row, "pnl_source", "unknown") or "unknown")] += 1

    summary = {
        "recordCount": len(rows),
        "openCount": sum(1 for row in rows if _trade_value(row, "status") == "open"),
        "closedCount": len(closed),
        "scoredCount": len(scored),
        "unscoredClosedCount": len(closed) - len(scored),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "winRatePct": round(len(wins) / len(scored) * 100, 2) if scored else None,
        "grossProfit": round(gross_profit, 2),
        "grossLoss": round(gross_loss, 2),
        "grossPnl": round(sum(item[1] for item in pnl_rows), 2),
        "recordedFees": round(sum(item[2] for item in pnl_rows), 2),
        "netPnlAfterRecordedFees": round(sum(item[3] for item in pnl_rows), 2),
        "expectancy": round(sum(item[3] for item in pnl_rows) / len(pnl_rows), 2) if pnl_rows else None,
        "averageWin": round(sum(item[3] for item in wins) / len(wins), 2) if wins else None,
        "averageLoss": round(sum(item[3] for item in losses) / len(losses), 2) if losses else None,
        "profitFactor": round(profit_factor, 3) if profit_factor is not None else None,
        "maxDrawdown": round(max_drawdown, 2),
        "feeCoveragePct": round(fees_known / len(scored) * 100, 2) if scored else None,
        "pnlSources": dict(sorted(pnl_sources.items())),
    }
    return summary


def build_benchmark(trades: Iterable[Any]) -> dict[str, Any]:
    rows = list(trades)
    groups: dict[str, dict[str, list[Any]]] = {
        "byStrategy": defaultdict(list),
        "bySymbol": defaultdict(list),
        "byMode": defaultdict(list),
    }
    for row in rows:
        if _trade_value(row, "status") != "closed":
            continue
        groups["byStrategy"][str(_trade_value(row, "strategy_version") or "unknown")].append(row)
        groups["bySymbol"][str(_trade_value(row, "symbol") or "unknown")].append(row)
        groups["byMode"][str(_trade_value(row, "mode") or "unknown")].append(row)

    return {
        "summary": summarize_trades(rows),
        **{
            key: [
                {"key": name, **summarize_trades(group)}
                for name, group in sorted(values.items())
            ]
            for key, values in groups.items()
        },
    }
