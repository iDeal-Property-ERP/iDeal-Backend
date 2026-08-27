from django.db import migrations
from django.db.models import F


def backfill_vas_translations(apps, schema_editor):
    ServiceCatalogItem = apps.get_model("vas", "ServiceCatalogItem")

    ServiceCatalogItem.objects.all().update(
        name_en=F("name"),
        name_uz=F("name"),
        name_ru=F("name"),
        description_en=F("description"),
        description_uz=F("description"),
        description_ru=F("description"),
    )


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("vas", "0003_servicecatalogitem_description_en_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_vas_translations, reverse_backfill),
    ]
