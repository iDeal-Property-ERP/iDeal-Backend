from django.db import migrations

from core.utils.html_sanitizer import sanitize_description_html


def normalize_property_descriptions(apps, schema_editor):
    Property = apps.get_model("property", "Property")
    for prop in Property.objects.all().iterator():
        updated = False
        for field in ("description", "description_en", "description_uz", "description_ru"):
            val = getattr(prop, field, None)
            if val is not None:
                sanitized = sanitize_description_html(val)
                if sanitized != val:
                    setattr(prop, field, sanitized)
                    updated = True
        if updated:
            prop.save(update_fields=["description", "description_en", "description_uz", "description_ru"])


def reverse_normalize(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0018_property_contact_phone_property_created_by"),
    ]

    operations = [
        migrations.RunPython(normalize_property_descriptions, reverse_normalize),
    ]
