# type: ignore
from django.db import migrations


def clear_banner_tags(apps, schema_editor):
    MobileHomeBanner = apps.get_model("mobile_config", "MobileHomeBanner")
    MobileHomeBanner.objects.filter(
        icon__in=["circle_check", "shield_check", "calendar_event", "file_certificate"]
    ).update(tag="", tag_en=None, tag_ru=None, tag_uz=None)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("mobile_config", "0003_seed_default_banners"),
    ]

    operations = [
        migrations.RunPython(clear_banner_tags, noop),
    ]
