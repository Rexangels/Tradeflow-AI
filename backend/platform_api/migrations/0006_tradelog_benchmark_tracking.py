from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_api", "0005_tradelog_exit_reason_tradelog_fee_paid_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradelog",
            name="closed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="tradelog",
            name="pnl_source",
            field=models.CharField(blank=True, default="unknown", max_length=32),
        ),
    ]
