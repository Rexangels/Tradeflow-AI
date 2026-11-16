import uuid

from django.contrib.auth.models import User
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Agent(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="agents")
    name = models.CharField(max_length=80)
    type = models.CharField(max_length=20)
    reward_style = models.CharField(max_length=20)
    risk_tolerance = models.FloatField()
    holding_behavior = models.CharField(max_length=20)
    strategies = models.JSONField(default=list)


class MarketDataSnapshot(models.Model):
    """Content-addressed, append-only record of the exact candles used in research."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="market_data_snapshots")
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=8)
    source = models.CharField(max_length=32, default="unknown")
    first_bar_at = models.DateTimeField()
    last_bar_at = models.DateTimeField()
    candle_count = models.PositiveIntegerField()
    retrieved_at = models.DateTimeField()
    content_sha256 = models.CharField(max_length=64)
    candles = models.JSONField(default=list)
    validation_report = models.JSONField(default=dict)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-retrieved_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "symbol", "timeframe", "content_sha256"),
                name="uniq_market_snapshot_owner_hash",
            ),
        ]
        indexes = [
            models.Index(
                fields=("owner", "symbol", "timeframe", "-retrieved_at"),
                name="market_snap_owner_sym_time_idx",
            ),
        ]


class BacktestRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="backtest_runs")
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="backtest_runs")
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=8)
    settings = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)
    validation = models.JSONField(default=dict)
    equity_curve = models.JSONField(default=list)
    snapshot = models.ForeignKey(
        "MarketDataSnapshot",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="backtest_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class BacktestTrade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    backtest_run = models.ForeignKey(BacktestRun, on_delete=models.CASCADE, related_name="trades")
    type = models.CharField(max_length=10)
    price = models.FloatField()
    executed_at = models.DateTimeField()
    quantity = models.FloatField()
    notional = models.FloatField()
    fee_paid = models.FloatField()
    profit = models.FloatField(null=True, blank=True)
    reason = models.CharField(max_length=160)


class PaperAccount(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name="paper_account")
    cash_balance = models.FloatField(default=10000)
    equity = models.FloatField(default=10000)
    realized_pnl = models.FloatField(default=0)


class PaperSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="paper_sessions")
    paper_account = models.ForeignKey(PaperAccount, on_delete=models.CASCADE, related_name="sessions")
    created_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)


class PaperOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="paper_orders")
    paper_account = models.ForeignKey(PaperAccount, on_delete=models.CASCADE, related_name="orders")
    session = models.ForeignKey(PaperSession, on_delete=models.CASCADE, related_name="orders")
    symbol = models.CharField(max_length=20)
    side = models.CharField(max_length=10)
    quantity = models.FloatField()
    fill_price = models.FloatField()
    notional = models.FloatField()
    fee_paid = models.FloatField()
    realized_pnl = models.FloatField(default=0)
    status = models.CharField(max_length=20, default="filled")
    created_at = models.DateTimeField(auto_now_add=True)


class PaperPosition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="paper_positions")
    paper_account = models.ForeignKey(PaperAccount, on_delete=models.CASCADE, related_name="positions")
    symbol = models.CharField(max_length=20)
    quantity = models.FloatField()
    average_entry_price = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("paper_account", "symbol")


class ChatThread(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_threads")
    agent = models.ForeignKey(Agent, on_delete=models.SET_NULL, null=True, blank=True, related_name="chat_threads")
    title = models.CharField(max_length=120, null=True, blank=True)


class ChatMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    thread = models.ForeignKey(ChatThread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20)
    content = models.TextField()
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class MarketDataCache(TimeStampedModel):
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=8)
    limit = models.PositiveIntegerField(default=500)
    payload = models.JSONField(default=list)

    class Meta:
        unique_together = ("symbol", "timeframe", "limit")


class UsageEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="usage_events")
    category = models.CharField(max_length=40)
    reference_id = models.CharField(max_length=64, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AppSetting(TimeStampedModel):
    key = models.CharField(max_length=80, unique=True)
    value = models.JSONField(default=dict)


class ForexPairConfig(TimeStampedModel):
    symbol = models.CharField(max_length=20, unique=True)
    is_watched = models.BooleanField(default=True)
    default_qty = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.symbol} ({'watched' if self.is_watched else 'ignored'})"


class RiskRule(TimeStampedModel):
    key = models.CharField(max_length=60, unique=True)
    value = models.JSONField(default=dict)

    def __str__(self):
        return self.key


EXIT_REASON_CHOICES = (
    ("", "unknown"),
    ("sl", "stop-loss"),
    ("tp", "take-profit"),
    ("opposite", "opposite-signal"),
    ("manual", "manual-close"),
    ("news", "news-guard"),
    ("session", "session-end"),
    ("eod", "end-of-data"),
)

LESSON_TAG_CHOICES = (
    ("", "none"),
    ("good-win", "good-win"),
    ("good-loss", "good-loss"),
    ("chased", "chased-entry"),
    ("early-m15", "early-m15"),
    ("news-slip", "news-slip"),
    ("spread-wide", "spread-widened"),
    ("sized-big", "sized-too-big"),
    ("no-setup", "no-setup"),
)


class TradeLog(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alpaca_order_id = models.CharField(max_length=64, unique=True, null=True, blank=True)
    agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.SET_NULL, related_name="trade_logs")
    symbol = models.CharField(max_length=20)
    side = models.CharField(max_length=10)  # buy | sell
    qty = models.FloatField()
    entry_price = models.FloatField(null=True, blank=True)
    exit_price = models.FloatField(null=True, blank=True)
    stop_loss = models.FloatField(null=True, blank=True)
    take_profit = models.FloatField(null=True, blank=True)
    realized_pnl = models.FloatField(null=True, blank=True)
    pnl_source = models.CharField(max_length=32, default="unknown", blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="open")  # open | closed | cancelled
    ai_reasoning = models.TextField(blank=True)
    mode = models.CharField(max_length=10, default="paper")  # paper | live
    # Journal v2: structured, queryable, migration-safe (all nullable/default).
    strategy_version = models.CharField(max_length=64, default="trend-breakout-v1/1.0.0")
    regime = models.CharField(max_length=32, default="", blank=True)
    votes = models.JSONField(default=dict, blank=True)
    session = models.CharField(max_length=64, default="", blank=True)
    news_state = models.CharField(max_length=16, default="", blank=True)  # CLEAR | BLOCKED
    spread_pips = models.FloatField(null=True, blank=True)
    fee_paid = models.FloatField(null=True, blank=True)
    mfe_r = models.FloatField(null=True, blank=True)
    mae_r = models.FloatField(null=True, blank=True)
    exit_reason = models.CharField(max_length=16, default="", blank=True)
    followed_plan = models.BooleanField(null=True, blank=True)
    lesson_tag = models.CharField(max_length=16, default="", blank=True)
    human_note = models.CharField(max_length=140, default="", blank=True)

    def __str__(self):
        return f"{self.side.upper()} {self.symbol} {self.qty} ({self.status})"


class AISignal(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(Agent, on_delete=models.CASCADE, related_name="signals")
    symbol = models.CharField(max_length=20)
    timeframe = models.CharField(max_length=8)
    direction = models.CharField(max_length=10)  # long | short | neutral
    confidence = models.FloatField(default=0.0)
    reasoning = models.TextField(blank=True)
    indicators = models.JSONField(default=dict)
    acted_on = models.BooleanField(default=False)
    trade_log = models.ForeignKey(TradeLog, null=True, blank=True, on_delete=models.SET_NULL, related_name="signals")

    def __str__(self):
        return f"{self.direction.upper()} {self.symbol} ({self.confidence:.2f})"
