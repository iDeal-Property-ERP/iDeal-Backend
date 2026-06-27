from django.db import migrations

FAQS = [
    (
        "Are all listings really verified?",
        "Yes. Our team checks ownership documents and inspects each property before it is "
        "published, so what you see is what exists.",
        10,
    ),
    (
        "Who pays the iDeal fee?",
        "The price you see is the price you pay — there are no agency markups for renters. "
        "iDeal is paid by owners out of the managed rental income.",
        20,
    ),
    (
        "Is the rental contract legally binding?",
        "Yes. Every rental is backed by an officially registered agreement generated and signed "
        "in-app, protecting both renters and owners.",
        30,
    ),
    (
        "What happens after I move in?",
        "iDeal manages the tenancy end-to-end — payments, maintenance, and support are all handled "
        "in the app for the duration of your stay.",
        40,
    ),
]


def backfill_listings(apps, schema_editor):
    Listing = apps.get_model("marketplace", "Listing")
    Listing.objects.filter(is_active=True).update(status="published")
    Listing.objects.filter(is_active=False).update(status="archived")
    for listing in Listing.objects.all().iterator():
        if listing.monthly_price is None and listing.listed_price is not None:
            listing.monthly_price = listing.listed_price
            listing.save(update_fields=["monthly_price"])


def seed_faqs(apps, schema_editor):
    FaqItem = apps.get_model("marketplace", "FaqItem")
    for question, answer, sort_order in FAQS:
        FaqItem.objects.get_or_create(
            question=question,
            defaults={"answer": answer, "sort_order": sort_order, "is_active": True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("marketplace", "0004_contactinquiry_faqitem_listing_currency_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_listings, noop),
        migrations.RunPython(seed_faqs, noop),
    ]
