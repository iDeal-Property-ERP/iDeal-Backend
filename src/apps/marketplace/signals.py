from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from marketplace.models import Listing
from property.models import Property

from core.constants import ListingStatus, PropertyStatus


def _publish(listing, instance):
    """Mirror status/is_active to PUBLISHED, stamping published_at on first publish."""
    listing.status = ListingStatus.PUBLISHED
    listing.is_active = True
    if listing.published_at is None:
        listing.published_at = timezone.now()
    listing.save(update_fields=["status", "is_active", "published_at", "updated_at"])


def _create_published_listing(instance):
    """Legacy auto-create path: a VACANT property with no listing gets a published one."""
    Listing.objects.create(
        property=instance,
        status=ListingStatus.PUBLISHED,
        is_active=True,
        description=instance.description,
        listed_price=instance.ask_price,
        monthly_price=instance.ask_price,
        published_at=timezone.now(),
    )


@receiver(post_save, sender=Property)
def manage_listing_on_property_change(sender, instance, created, update_fields, **kwargs):
    """Keep a property's Listing in sync with its status.

    Idempotent + status-aware so the wizard's draft/review lifecycle is never bypassed:
    - On property→VACANT we only publish an *existing* listing when it has passed review
      (status == PENDING_REVIEW). Drafts / rejected / archived listings are left untouched.
    - Auto-create only happens for the legacy path where a VACANT property has no listing
      at all (e.g. management-created properties that never went through the wizard).
    """
    if created and instance.status == PropertyStatus.VACANT:
        _create_published_listing(instance)
        return

    if created:
        return

    status_in_update = update_fields is None or "status" in update_fields
    if not status_in_update:
        return

    if instance.status == PropertyStatus.VACANT:
        try:
            listing = instance.listing
        except Listing.DoesNotExist:
            _create_published_listing(instance)
            return
        # Only publish if the listing has been reviewed/approved, or was already published.
        if listing.status in (ListingStatus.PENDING_REVIEW, ListingStatus.PUBLISHED):
            _publish(listing, instance)
        # DRAFT / REJECTED / ARCHIVED listings are intentionally not resurrected here.
    elif instance.status == PropertyStatus.RENTED:
        try:
            listing = instance.listing
        except Listing.DoesNotExist:
            return
        # Rented is a *temporary* unavailability — keep the PUBLISHED lifecycle state so the
        # listing republishes automatically when the lease ends and the property is vacant
        # again. Only flip the availability flag. (ARCHIVED is reserved for owner action.)
        if listing.status == ListingStatus.PUBLISHED and listing.is_active:
            listing.is_active = False
            listing.save(update_fields=["is_active", "updated_at"])
