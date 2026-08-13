# Generated manually; variants are intentionally populated only by future normal photo saves.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0011_property_floor_within_total_floors"),
    ]

    operations = [
        migrations.AddField(
            model_name="propertyphoto",
            name="display_image",
            field=models.ImageField(blank=True, null=True, upload_to="properties/photos/"),
        ),
        migrations.AddField(
            model_name="propertyphoto",
            name="preview_image",
            field=models.ImageField(blank=True, null=True, upload_to="properties/photos/"),
        ),
    ]
