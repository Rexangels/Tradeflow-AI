from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("platform_api", "0002_paperorder_realized_pnl"),
    ]

    operations = [
        migrations.AddField(
            model_name="backtestrun",
            name="validation",
            field=models.JSONField(default=dict),
        ),
    ]
