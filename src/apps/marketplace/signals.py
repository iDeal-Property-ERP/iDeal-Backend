from django.db.models.signals import post_save
from django.dispatch import receiver
from marketplace.models import Listing
from property.models import Property

from core.constants import PropertyStatus


@receiver(post_save, sender=Property)
def manage_listing_on_property_change(sender, instance, created, update_fields, **kwargs):
    if created and instance.status == PropertyStatus.VACANT:
        Listing.objects.create(
            property=instance,
            is_active=True,
            description=instance.description,
            listed_price=instance.ask_price,
        )
        return

    if not created:
        status_in_update = update_fields is None or "status" in update_fields
        if not status_in_update:
            return

        if instance.status == PropertyStatus.VACANT:
            try:
                listing = instance.listing
                listing.is_active = True
                listing.save(update_fields=["is_active", "updated_at"])
            except Listing.DoesNotExist:
                Listing.objects.create(
                    property=instance,
                    is_active=True,
                    description=instance.description,
                    listed_price=instance.ask_price,
                )
        elif instance.status == PropertyStatus.RENTED:
            try:
                listing = instance.listing
                listing.is_active = False
                listing.save(update_fields=["is_active", "updated_at"])
            except Listing.DoesNotExist:
                pass
