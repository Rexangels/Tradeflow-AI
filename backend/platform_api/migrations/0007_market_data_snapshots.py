import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("platform_api", "0006_tradelog_benchmark_tracking"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketDataSnapshot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("symbol", models.CharField(max_length=20)),
                ("timeframe", models.CharField(max_length=8)),
                ("source", models.CharField(default="unknown", max_length=32)),
                ("first_bar_at", models.DateTimeField()),
                ("last_bar_at", models.DateTimeField()),
                ("candle_count", models.PositiveIntegerField()),
                ("retrieved_at", models.DateTimeField()),
                ("content_sha256", models.CharField(max_length=64)),
                ("candles", models.JSONField(default=list)),
                ("validation_report", models.JSONField(default=dict)),
                ("metadata", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="market_data_snapshots",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ("-retrieved_at",),
            },
        ),
        migrations.AddField(
            model_name="backtestrun",
            name="snapshot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="backtest_runs",
                to="platform_api.marketdatasnapshot",
            ),
        ),
        migrations.AddConstraint(
            model_name="marketdatasnapshot",
            constraint=models.UniqueConstraint(
                fields=("owner", "symbol", "timeframe", "content_sha256"),
                name="uniq_market_snapshot_owner_hash",
            ),
        ),
        migrations.AddIndex(
            model_name="marketdatasnapshot",
            index=models.Index(
                fields=["owner", "symbol", "timeframe", "-retrieved_at"],
                name="market_snap_owner_sym_time_idx",
            ),
        ),
    ]
