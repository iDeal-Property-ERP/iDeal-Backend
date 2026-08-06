from django.db.models.signals import post_save
from django.dispatch import receiver
from finance.models import Payment
from finance.services import allocate_paid_rent

from core.constants import PaymentStatus


@receiver(post_save, sender=Payment)
def accrue_payout_on_paid_payment(sender, instance, **kwargs):
    """Allocate paid rent to its agreement-month settlement.

    Runs on every save path (mark-paid, partial update, tenant pay-now, admin).
    Idempotency is enforced by receipt allocations.
    """
    if instance.status == PaymentStatus.PAID:
        allocate_paid_rent(instance)
