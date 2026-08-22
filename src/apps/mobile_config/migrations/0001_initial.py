# pyright: reportArgumentType=false, reportGeneralTypeIssues=false
import django.db.models.deletion
from django.db import migrations, models

import core.constants


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MobileUpdatePolicy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                (
                    "platform",
                    models.CharField(
                        choices=core.constants.DevicePlatform.choices,
                        db_index=True,
                        max_length=20,
                        verbose_name="Platform",
                    ),
                ),
                ("latest_version", models.CharField(max_length=32, verbose_name="Latest Version")),
                ("store_url", models.URLField(max_length=500, verbose_name="Store URL")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is Active")),
            ],
            options={
                "verbose_name": "Mobile Update Policy",
                "verbose_name_plural": "Mobile Update Policies",
                "db_table": "mobile_update_policies",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MobileCriticalUpdateRange",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("minimum_version", models.CharField(max_length=32, verbose_name="Minimum Version")),
                ("maximum_version", models.CharField(max_length=32, verbose_name="Maximum Version")),
                ("is_active", models.BooleanField(db_index=True, default=True, verbose_name="Is Active")),
                (
                    "policy",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="critical_ranges",
                        to="mobile_config.mobileupdatepolicy",
                        verbose_name="Policy",
                    ),
                ),
            ],
            options={
                "verbose_name": "Mobile Critical Update Range",
                "verbose_name_plural": "Mobile Critical Update Ranges",
                "db_table": "mobile_critical_update_ranges",
                "ordering": ["minimum_version", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="mobileupdatepolicy",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_active", True)),
                fields=("platform",),
                name="unique_active_policy_per_platform",
            ),
        ),
    ]
