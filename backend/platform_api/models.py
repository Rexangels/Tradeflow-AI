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
