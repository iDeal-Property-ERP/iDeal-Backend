from django.db import migrations

from core.utils.html_sanitizer import sanitize_description_html


def normalize_listing_descriptions(apps, schema_editor):
    Listing = apps.get_model("marketplace", "Listing")
    for listing in Listing.objects.all().iterator():
        updated = False
        for field in ("description", "description_en", "description_uz", "description_ru"):
            val = getattr(listing, field, None)
            if val is not None:
                sanitized = sanitize_description_html(val)
                if sanitized != val:
                    setattr(listing, field, sanitized)
                    updated = True
        if updated:
            listing.save(update_fields=["description", "description_en", "description_uz", "description_ru"])


def reverse_normalize(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0013_backfill_translations"),
    ]

    operations = [
        migrations.RunPython(normalize_listing_descriptions, reverse_normalize),
    ]
