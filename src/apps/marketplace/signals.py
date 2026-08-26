from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from marketplace.models import Listing
from property.models import Property

from core.constants import ListingStatus, OneOffChannel, PropertyEngagementType, PropertyStatus


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


def _one_off_is_off_market(instance):
    """Off-market brokerage inventory must never surface through a Listing."""
    if instance.engagement_type != PropertyEngagementType.ONE_OFF:
        return False
    try:
        return instance.one_off_deal.channel == OneOffChannel.OFF_MARKET
    except Exception:
        # The property is created before its paired deal inside one transaction.
        return False


@receiver(post_save, sender=Property)
def manage_listing_on_property_change(sender, instance, created, update_fields, **kwargs):
    """Keep an existing Listing in sync with property status and metadata."""
    if instance.engagement_type == PropertyEngagementType.ONE_OFF:
        return

    if created and instance.status == PropertyStatus.VACANT:
        _create_published_listing(instance)
        return

    if created:
        return

    if not created:
        try:
            listing = instance.listing
            # Sync metadata to the marketplace listing
            sync_fields = []
            if listing.description != instance.description:
                listing.description = instance.description
                sync_fields.append("description")
            if listing.monthly_price != instance.ask_price:
                listing.monthly_price = instance.ask_price
                listing.listed_price = instance.ask_price
                sync_fields.extend(["monthly_price", "listed_price"])
            if sync_fields:
                sync_fields.append("updated_at")
                listing.save(update_fields=sync_fields)
        except Listing.DoesNotExist:
            pass

    status_in_update = update_fields is None or "status" in update_fields
    if not status_in_update:
        return

    if instance.status == PropertyStatus.VACANT:
        try:
            listing = instance.listing
        except Listing.DoesNotExist:
            return
        # Only publish if the listing has been reviewed/approved, or was already published.
        if listing.status in (ListingStatus.PENDING_REVIEW, ListingStatus.PUBLISHED):
            _publish(listing, instance)
        # REJECTED / ARCHIVED listings are intentionally not resurrected here.
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
