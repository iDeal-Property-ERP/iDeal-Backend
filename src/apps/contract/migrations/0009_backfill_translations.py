from django.db import migrations
from django.db.models import F


def backfill_contract_translations(apps, schema_editor):
    PublicOffer = apps.get_model("contract", "PublicOffer")
    OwnerAgreement = apps.get_model("contract", "OwnerAgreement")
    OwnerOnboarding = apps.get_model("contract", "OwnerOnboarding")

    PublicOffer.objects.all().update(
        body_en=F("body"),
        body_uz=F("body"),
        body_ru=F("body"),
    )

    OwnerAgreement.objects.filter(accepted_locale="").update(accepted_locale="en")
    OwnerOnboarding.objects.filter(offer_accepted_locale="").update(offer_accepted_locale="en")


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("contract", "0008_owneragreement_accepted_locale_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_contract_translations, reverse_backfill),
    ]
