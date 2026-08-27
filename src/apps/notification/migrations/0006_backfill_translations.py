from django.db import migrations
from django.db.models import F


def backfill_notification_translations(apps, schema_editor):
    Notification = apps.get_model("notification", "Notification")

    Notification.objects.all().update(
        title_en=F("title"),
        title_uz=F("title"),
        title_ru=F("title"),
        body_en=F("body"),
        body_uz=F("body"),
        body_ru=F("body"),
    )


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("notification", "0005_notification_body_en_notification_body_ru_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_notification_translations, reverse_backfill),
    ]
