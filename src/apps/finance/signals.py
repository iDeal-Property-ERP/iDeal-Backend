from django.db.models.signals import post_save
from django.dispatch import receiver
from finance.models import Payment
from finance.services import accrue_owner_payout_for_payment

from core.constants import PaymentStatus


@receiver(post_save, sender=Payment)
def accrue_payout_on_paid_payment(sender, instance, **kwargs):
    """Accrue an owner payout whenever a payment is (or becomes) PAID.

    Runs on every save path (mark-paid, partial update, tenant pay-now, admin).
    Idempotency is enforced in :func:`accrue_owner_payout_for_payment`.
    """
    if instance.status == PaymentStatus.PAID:
        accrue_owner_payout_for_payment(instance)
