# Generated manually for floor-bound data repair and enforcement.

from django.db import migrations, models
from django.db.models import F, Q


def repair_floors(apps, schema_editor):
    """Clamp invalid floors without changing updated_at; historical managers include soft-deleted rows."""
    Property = apps.get_model("property", "Property")
    Property.objects.filter(total_floors__isnull=False, floor__gt=F("total_floors")).update(floor=F("total_floors"))


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0010_remove_property_bathrooms"),
    ]

    operations = [
        migrations.RunPython(repair_floors, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="property",
            constraint=models.CheckConstraint(
                condition=Q(floor__isnull=True) | Q(total_floors__isnull=True) | Q(floor__lte=F("total_floors")),
                name="property_floor_lte_total_floors",
            ),
        ),
    ]
