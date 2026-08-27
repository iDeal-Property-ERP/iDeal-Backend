from django.db import migrations
from django.db.models import F


def backfill_marketplace_translations(apps, schema_editor):
    Listing = apps.get_model("marketplace", "Listing")
    FaqItem = apps.get_model("marketplace", "FaqItem")

    Listing.objects.all().update(
        description_en=F("description"),
        description_uz=F("description"),
        description_ru=F("description"),
    )

    FaqItem.objects.all().update(
        question_en=F("question"),
        question_uz=F("question"),
        question_ru=F("question"),
        answer_en=F("answer"),
        answer_uz=F("answer"),
        answer_ru=F("answer"),
    )


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0012_faqitem_answer_en_faqitem_answer_ru_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_marketplace_translations, reverse_backfill),
    ]
