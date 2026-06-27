from django.db import migrations

AMENITIES = [
    ("wifi", "High-speed Wi-Fi", "wifi", 10),
    ("air_conditioning", "Air conditioning", "snowflake", 20),
    ("parking", "Free parking", "car", 30),
    ("elevator", "Elevator", "elevator", 40),
    ("balcony", "Balcony", "balcony", 50),
    ("furnished_kitchen", "Furnished kitchen", "kitchen", 60),
    ("security", "Security & intercom", "shield", 70),
    ("heating", "Central heating", "flame", 80),
    ("pets_allowed", "Pets allowed", "paw", 90),
]


def seed_amenities(apps, schema_editor):
    Amenity = apps.get_model("property", "Amenity")
    for slug, name, icon, sort_order in AMENITIES:
        Amenity.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "icon": icon, "sort_order": sort_order, "is_active": True},
        )


def backfill_verified(apps, schema_editor):
    """Mark properties that already have an active owner agreement as verified
    (they are contract-backed)."""
    Property = apps.get_model("property", "Property")
    OwnerAgreement = apps.get_model("contract", "OwnerAgreement")
    verified_property_ids = (
        OwnerAgreement.objects.filter(status="active").values_list("property_id", flat=True).distinct()
    )
    Property.objects.filter(id__in=list(verified_property_ids)).update(is_verified=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("property", "0002_amenity_property_bathrooms_property_deposit_amount_and_more"),
        ("contract", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_amenities, noop),
        migrations.RunPython(backfill_verified, noop),
    ]
