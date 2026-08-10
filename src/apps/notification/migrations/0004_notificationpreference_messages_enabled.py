from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notification", "0003_backfill_notification_audience"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationpreference",
            name="messages_enabled",
            field=models.BooleanField(default=True, verbose_name="Messages Enabled"),
        ),
    ]
