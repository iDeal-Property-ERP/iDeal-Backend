import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contract", "0006_remove_owneragreement_owner_guaranteed_amount_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="owneragreement",
            name="previous_agreement",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="renewed_agreement",
                to="contract.owneragreement",
                verbose_name="Previous Agreement",
            ),
        ),
        migrations.CreateModel(
            name="LeaseAgreementSegment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted At")),
                ("restored_at", models.DateTimeField(blank=True, null=True, verbose_name="Restored At")),
                ("transaction_id", models.UUIDField(blank=True, null=True, verbose_name="Transaction ID")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                (
                    "lease",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="agreement_segments",
                        to="contract.lease",
                    ),
                ),
                (
                    "owner_agreement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="lease_segments",
                        to="contract.owneragreement",
                    ),
                ),
            ],
            options={
                "verbose_name": "Lease Agreement Segment",
                "verbose_name_plural": "Lease Agreement Segments",
                "db_table": "lease_agreement_segments",
                "ordering": ["start_date"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("lease", "owner_agreement", "start_date"), name="unique_lease_agreement_segment"
                    )
                ],
            },
        ),
    ]
