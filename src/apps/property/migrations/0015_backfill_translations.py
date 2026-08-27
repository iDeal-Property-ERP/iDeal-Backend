from django.db import migrations
from django.db.models import F


def backfill_property_translations(apps, schema_editor):
    District = apps.get_model("property", "District")
    Amenity = apps.get_model("property", "Amenity")
    Property = apps.get_model("property", "Property")
    PropertyPhoto = apps.get_model("property", "PropertyPhoto")

    District.objects.all().update(
        name_en=F("name"),
        name_uz=F("name"),
        name_ru=F("name"),
        city_en=F("city"),
        city_uz=F("city"),
        city_ru=F("city"),
    )

    Amenity.objects.all().update(
        name_en=F("name"),
        name_uz=F("name"),
        name_ru=F("name"),
    )

    Property.objects.all().update(
        name_en=F("name"),
        name_uz=F("name"),
        name_ru=F("name"),
        description_en=F("description"),
        description_uz=F("description"),
        description_ru=F("description"),
    )

    PropertyPhoto.objects.all().update(
        caption_en=F("caption"),
        caption_uz=F("caption"),
        caption_ru=F("caption"),
    )


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0014_amenity_name_en_amenity_name_ru_amenity_name_uz_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_property_translations, reverse_backfill),
    ]
