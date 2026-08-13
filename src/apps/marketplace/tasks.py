from contract.models import Lease
from django.db import transaction
from django.utils import timezone
from marketplace.services.booking import BookingService

from core.constants import LeaseStatus


def expire_booking_holds() -> int:
    return BookingService.expire_stale_holds()


@transaction.atomic
def sync_lease_statuses() -> dict:
    today = timezone.localdate()
    expired = 0
    activated = 0
    for lease in Lease.objects.select_for_update().filter(
        status__in=[LeaseStatus.ACTIVE, LeaseStatus.SCHEDULED], end_date__lt=today
    ):
        lease.status = LeaseStatus.EXPIRED
        lease.save(update_fields=["status", "updated_at"])
        expired += 1
    for lease in Lease.objects.select_for_update().filter(status=LeaseStatus.SCHEDULED, start_date__lte=today):
        lease.status = LeaseStatus.ACTIVE
        lease.save(update_fields=["status", "updated_at"])
        activated += 1
    return {"expired": expired, "activated": activated}
