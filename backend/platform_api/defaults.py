DEFAULT_STRATEGIES = [
    {
        "id": "trend-following",
        "name": "Trend Following",
        "description": "EMA crossover entries with momentum-aware exits.",
        "enabled": True,
    },
    {
        "id": "mean-reversion",
        "name": "Mean Reversion",
        "description": "Bollinger Band fades filtered by RSI exhaustion.",
        "enabled": False,
    },
]

DEFAULT_AGENT = {
    "name": "Trend Research Template",
    "type": "template",
    "rewardStyle": "balanced",
    "riskTolerance": 0.4,
    "holdingBehavior": "short-term",
    "strategies": DEFAULT_STRATEGIES,
}
