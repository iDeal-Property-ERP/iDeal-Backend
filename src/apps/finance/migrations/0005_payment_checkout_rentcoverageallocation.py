import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contract", "0007_owneragreement_previous_agreement_and_more"),
        ("finance", "0004_remove_payoutschedule_source_payment_payment_kind_and_more"),
        ("marketplace", "0007_alter_booking_status_bookingquote_paymentcheckout_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="checkout",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="payments",
                to="marketplace.paymentcheckout",
                verbose_name="Payment Checkout",
            ),
        ),
        migrations.CreateModel(
            name="RentCoverageAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                (
                    "owner_agreement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rent_coverage_allocations",
                        to="contract.owneragreement",
                    ),
                ),
                (
                    "payment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="coverage_allocations",
                        to="finance.payment",
                    ),
                ),
            ],
            options={
                "db_table": "rent_coverage_allocations",
                "ordering": ["start_date"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("payment", "owner_agreement", "start_date"),
                        name="unique_payment_agreement_coverage",
                    )
                ],
            },
        ),
    ]
