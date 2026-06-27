from decimal import Decimal

from django.db import migrations


def seed_ratings(apps, schema_editor):
    """Backfill realistic-looking score/review_count for rows that have none.

    Deterministic from the pk so values are stable across environments. Does not
    overwrite any property that already has a real score/review_count.
    """
    Property = apps.get_model("property", "Property")
    for prop in Property.objects.all():
        changed = []
        # Set a 10-point score where missing or on the old 5-point mock scale (< 6).
        if prop.score is None or prop.score < 6:
            prop.score = Decimal("8.0") + Decimal(prop.pk % 20) / Decimal(10)
            changed.append("score")
        if not prop.review_count:
            prop.review_count = 12 + (prop.pk % 90)
            changed.append("review_count")
        if changed:
            prop.save(update_fields=changed)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0005_property_review_count"),
    ]

    operations = [
        migrations.RunPython(seed_ratings, noop),
    ]
