import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.constants


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0006_listing_minimum_stay_listing_price_includes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="booking",
            name="status",
            field=models.CharField(
                choices=core.constants.BookingStatus.choices,
                default="requested",
                max_length=32,
                verbose_name="Status",
            ),
        ),
        migrations.CreateModel(
            name="BookingQuote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted At")),
                ("restored_at", models.DateTimeField(blank=True, null=True, verbose_name="Restored At")),
                ("transaction_id", models.UUIDField(blank=True, null=True, verbose_name="Transaction ID")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("currency", models.CharField(max_length=3)),
                ("monthly_rent", models.DecimalField(decimal_places=2, max_digits=12)),
                ("deposit_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("first_period_rent", models.DecimalField(decimal_places=2, max_digits=12)),
                ("full_stay_rent", models.DecimalField(decimal_places=2, max_digits=12)),
                ("first_month_total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("full_stay_total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("periods", models.JSONField(default=list)),
                ("agreement_ids", models.JSONField(default=list)),
                ("fx_rate", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "listing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="booking_quotes",
                        to="marketplace.listing",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="booking_quotes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Booking Quote",
                "verbose_name_plural": "Booking Quotes",
                "db_table": "booking_quotes",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PaymentCheckout",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted At")),
                ("restored_at", models.DateTimeField(blank=True, null=True, verbose_name="Restored At")),
                ("transaction_id", models.UUIDField(blank=True, null=True, verbose_name="Transaction ID")),
                ("public_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("idempotency_key", models.CharField(max_length=128)),
                ("provider", models.CharField(choices=core.constants.PaymentProvider.choices, max_length=20)),
                (
                    "status",
                    models.CharField(
                        choices=core.constants.PaymentCheckoutStatus.choices, default="pending", max_length=32
                    ),
                ),
                ("pay_full_stay", models.BooleanField(default=False)),
                ("original_amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("original_currency", models.CharField(max_length=3)),
                ("provider_amount", models.DecimalField(decimal_places=2, max_digits=18)),
                ("provider_currency", models.CharField(max_length=3)),
                ("fx_rate", models.DecimalField(blank=True, decimal_places=6, max_digits=18, null=True)),
                ("checkout_url", models.URLField(max_length=1000)),
                ("external_id", models.CharField(blank=True, max_length=255, null=True)),
                ("expires_at", models.DateTimeField()),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "booking",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_checkout",
                        to="marketplace.booking",
                    ),
                ),
                (
                    "quote",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="checkouts",
                        to="marketplace.bookingquote",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_checkouts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Payment Checkout",
                "verbose_name_plural": "Payment Checkouts",
                "db_table": "payment_checkouts",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ProviderEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Created At")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Updated At")),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True, verbose_name="Deleted At")),
                ("restored_at", models.DateTimeField(blank=True, null=True, verbose_name="Restored At")),
                ("transaction_id", models.UUIDField(blank=True, null=True, verbose_name="Transaction ID")),
                ("provider", models.CharField(choices=core.constants.PaymentProvider.choices, max_length=20)),
                ("external_event_id", models.CharField(max_length=255)),
                ("event_type", models.CharField(max_length=100)),
                ("payload", models.JSONField(default=dict)),
                ("result", models.JSONField(default=dict)),
                (
                    "checkout",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="provider_events",
                        to="marketplace.paymentcheckout",
                    ),
                ),
            ],
            options={
                "verbose_name": "Provider Event",
                "verbose_name_plural": "Provider Events",
                "db_table": "provider_events",
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="bookingquote",
            index=models.Index(fields=["listing", "expires_at"], name="booking_quo_listing_d87514_idx"),
        ),
        migrations.AddIndex(
            model_name="bookingquote",
            index=models.Index(fields=["tenant", "expires_at"], name="booking_quo_tenant__0ea199_idx"),
        ),
        migrations.AddIndex(
            model_name="paymentcheckout",
            index=models.Index(fields=["status", "expires_at"], name="payment_che_status_653ff1_idx"),
        ),
        migrations.AddIndex(
            model_name="paymentcheckout",
            index=models.Index(fields=["provider", "external_id"], name="payment_che_provide_6e7802_idx"),
        ),
        migrations.AddConstraint(
            model_name="paymentcheckout",
            constraint=models.UniqueConstraint(fields=("tenant", "idempotency_key"), name="unique_tenant_checkout_key"),
        ),
        migrations.AddConstraint(
            model_name="providerevent",
            constraint=models.UniqueConstraint(fields=("provider", "external_event_id"), name="unique_provider_event"),
        ),
    ]
