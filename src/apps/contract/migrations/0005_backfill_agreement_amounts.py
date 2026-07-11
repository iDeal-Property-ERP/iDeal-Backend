# Data migration: backfill the snapshotted agreement amounts from the linked
# Property's current prices (best available approximation for legacy rows).
from django.db import migrations


def backfill_amounts(apps, schema_editor):
    OwnerAgreement = apps.get_model("contract", "OwnerAgreement")
    for agreement in OwnerAgreement.objects.select_related("property").filter(
        owner_guaranteed_amount__isnull=True
    ) | OwnerAgreement.objects.select_related("property").filter(tenant_charge_amount__isnull=True):
        prop = agreement.property
        changed = []
        if agreement.owner_guaranteed_amount is None and prop.owner_guaranteed_price is not None:
            agreement.owner_guaranteed_amount = prop.owner_guaranteed_price
            changed.append("owner_guaranteed_amount")
        if agreement.tenant_charge_amount is None and prop.tenant_charge_price is not None:
            agreement.tenant_charge_amount = prop.tenant_charge_price
            changed.append("tenant_charge_amount")
        if changed:
            agreement.save(update_fields=changed)


def noop(apps, schema_editor):
    """Reverse: keep the backfilled values (fields are dropped by 0004's reverse)."""


class Migration(migrations.Migration):
    dependencies = [
        ("contract", "0004_owneragreement_owner_guaranteed_amount_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_amounts, noop),
    ]
