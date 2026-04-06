from __future__ import annotations

from typing import Any

from .models import Agent, BacktestRun, ChatMessage, PaperOrder, PaperPosition


def serialize_agent(agent: Agent) -> dict[str, Any]:
    return {
        "id": str(agent.id),
        "name": agent.name,
        "type": agent.type,
        "rewardStyle": agent.reward_style,
        "riskTolerance": agent.risk_tolerance,
        "holdingBehavior": agent.holding_behavior,
        "strategies": agent.strategies,
        "createdAt": agent.created_at.isoformat(),
        "updatedAt": agent.updated_at.isoformat(),
    }


def serialize_backtest(run: BacktestRun) -> dict[str, Any]:
    stored_validation = run.validation or {
        "candlesChecked": len(run.equity_curve),
        "isSorted": True,
        "warnings": [],
    }
    validation = dict(stored_validation)
    walk_forward = validation.pop("walkForward", None) or {
        "available": False,
        "verdict": "unavailable",
        "trainCandlesPerWindow": 0,
        "testCandlesPerWindow": 0,
        "windowCount": 0,
        "benchmarkBeatRatePct": 0,
        "profitableWindowPct": 0,
        "averageTestReturnPct": 0,
        "averageTestBenchmarkReturnPct": 0,
        "averageTestExcessReturnPct": 0,
        "averageTestSharpeRatio": 0,
        "averageTestDrawdownPct": 0,
        "warnings": ["Walk-forward data is not available for this run."],
        "windows": [],
    }
    model_analysis = validation.pop("modelAnalysis", None) or {
        "available": False,
        "modelType": "baseline_logistic_regression",
        "labelHorizonBars": 0,
        "trainSamples": 0,
        "testSamples": 0,
        "featuresUsed": [],
        "performance": {
            "trainAccuracyPct": 0,
            "testAccuracyPct": 0,
            "testPrecisionPct": 0,
            "testRecallPct": 0,
            "testAverageForwardReturnPct": 0,
            "predictedLongHitRatePct": 0,
        },
        "signal": {
            "asOf": run.created_at.isoformat(),
            "action": "hold",
            "confidencePct": 0,
            "probabilityUpPct": 50,
            "probabilityDownPct": 50,
        },
        "topFeatures": [],
        "explanation": {
            "summary": "Model analysis is not available for this run.",
            "reasoning": [],
            "caveats": ["Run a fresh backtest to generate model analysis."],
            "asOf": run.created_at.isoformat(),
        },
        "tuning": {
            "enabled": False,
            "adaptationMode": "scheduled_retrain",
            "objective": "validation_quality_score",
            "candidateCount": 0,
            "trainSamples": 0,
            "validationSamples": 0,
            "testSamples": 0,
            "selectedConfig": {
                "horizonBars": 0,
                "learningRate": 0,
                "regularization": 0,
                "buyThreshold": 0,
                "sellThreshold": 0,
                "epochs": 0,
            },
            "bestValidationScore": 0,
            "validationPerformance": {
                "accuracyPct": 0,
                "precisionPct": 0,
                "recallPct": 0,
                "predictedLongHitRatePct": 0,
                "predictedLongCount": 0,
                "averageForwardReturnPct": 0,
            },
            "topTrials": [],
        },
    }
    return {
        "id": str(run.id),
        "symbol": run.symbol,
        "timeframe": run.timeframe,
        "agent": serialize_agent(run.agent),
        "settings": run.settings,
        "metrics": run.metrics,
        "validation": validation,
        "walkForward": walk_forward,
        "modelAnalysis": model_analysis,
        "equityCurve": run.equity_curve,
        "trades": [
            {
                "id": str(trade.id),
                "type": trade.type,
                "price": trade.price,
                "time": trade.executed_at.isoformat(),
                "quantity": trade.quantity,
                "notional": trade.notional,
                "feePaid": trade.fee_paid,
                "profit": trade.profit,
                "reason": trade.reason,
            }
            for trade in run.trades.order_by("executed_at")
        ],
        "createdAt": run.created_at.isoformat(),
    }


def serialize_paper_order(order: PaperOrder) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "symbol": order.symbol,
        "side": order.side,
        "quantity": order.quantity,
        "fillPrice": order.fill_price,
        "notional": order.notional,
        "feePaid": order.fee_paid,
        "realizedPnl": order.realized_pnl,
        "status": order.status,
        "createdAt": order.created_at.isoformat(),
    }


def serialize_position(position: PaperPosition, market_price: float) -> dict[str, Any]:
    market_value = round(position.quantity * market_price, 4)
    unrealized_pnl = round((market_price - position.average_entry_price) * position.quantity, 4)
    return {
        "id": str(position.id),
        "symbol": position.symbol,
        "quantity": round(position.quantity, 8),
        "averageEntryPrice": round(position.average_entry_price, 4),
        "marketPrice": round(market_price, 4),
        "marketValue": market_value,
        "unrealizedPnl": unrealized_pnl,
        "updatedAt": position.updated_at.isoformat(),
    }


def serialize_chat_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "createdAt": message.created_at.isoformat(),
    }
