DEFAULT_STRATEGIES = [
    {
        "id": "trend-breakout-v1",
        "name": "Trend Breakout v1",
        "description": "H4 bias -> H1 confirm -> M15 trigger with ATR stops, regime gate, next-bar fills.",
        "enabled": True,
    },
    {
        "id": "trend-following",
        "name": "Trend Following (legacy)",
        "description": "EMA crossover entries with momentum-aware exits. Kept for backward compatibility.",
        "enabled": False,
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
