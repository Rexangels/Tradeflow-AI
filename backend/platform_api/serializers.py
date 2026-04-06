from rest_framework import serializers


TIMEFRAME_CHOICES = ("1m", "5m", "15m", "1h", "4h", "1d")
REWARD_STYLE_CHOICES = ("aggressive", "balanced", "conservative")
HOLDING_BEHAVIOR_CHOICES = ("short-term", "swing", "long-term")
TYPE_CHOICES = ("template", "custom")


class StrategySerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    enabled = serializers.BooleanField()


class AgentPayloadSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    name = serializers.CharField(min_length=2, max_length=80)
    type = serializers.ChoiceField(choices=TYPE_CHOICES)
    rewardStyle = serializers.ChoiceField(choices=REWARD_STYLE_CHOICES)
    riskTolerance = serializers.FloatField(min_value=0, max_value=1)
    holdingBehavior = serializers.ChoiceField(choices=HOLDING_BEHAVIOR_CHOICES)
    strategies = StrategySerializer(many=True, min_length=1)


class MarketDataQuerySerializer(serializers.Serializer):
    symbol = serializers.CharField(min_length=3)
    timeframe = serializers.ChoiceField(choices=TIMEFRAME_CHOICES)
    limit = serializers.IntegerField(min_value=50, max_value=1000, default=500)
    forceRefresh = serializers.BooleanField(default=False)


class BacktestSettingsSerializer(serializers.Serializer):
    startingBalance = serializers.FloatField(min_value=1, default=10000)
    feeRate = serializers.FloatField(min_value=0, max_value=0.02, default=0.001)
    slippageRate = serializers.FloatField(min_value=0, max_value=0.02, default=0.0005)
    positionSizeFraction = serializers.FloatField(min_value=0.05, max_value=1, default=0.95)


class BacktestRequestSerializer(serializers.Serializer):
    symbol = serializers.CharField(min_length=3)
    timeframe = serializers.ChoiceField(choices=TIMEFRAME_CHOICES)
    limit = serializers.IntegerField(required=False, min_value=50, max_value=1000, default=500)
    candles = serializers.ListField(required=False)
    agent = AgentPayloadSerializer()
    settings = BacktestSettingsSerializer(required=False)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8)


class PaperOrderSerializer(serializers.Serializer):
    symbol = serializers.CharField(min_length=3)
    side = serializers.ChoiceField(choices=("buy", "sell"))
    quantity = serializers.FloatField(required=False, min_value=0.00000001)
    notional = serializers.FloatField(required=False, min_value=1)
    timeframe = serializers.ChoiceField(choices=TIMEFRAME_CHOICES, default="1h")
    sessionId = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if not attrs.get("quantity") and not attrs.get("notional"):
            raise serializers.ValidationError("quantity or notional is required")
        return attrs


class AiChatSerializer(serializers.Serializer):
    threadId = serializers.UUIDField(required=False)
    message = serializers.CharField()
    symbol = serializers.CharField(required=False)
    timeframe = serializers.ChoiceField(choices=TIMEFRAME_CHOICES, required=False)
    agentId = serializers.UUIDField(required=False)
    backtestId = serializers.UUIDField(required=False)
    tradeId = serializers.UUIDField(required=False)
    replayTime = serializers.DateTimeField(required=False)
    playbackIndex = serializers.IntegerField(required=False, min_value=0)
