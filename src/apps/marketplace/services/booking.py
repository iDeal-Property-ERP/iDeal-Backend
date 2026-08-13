from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from contract.models import Lease, LeaseAgreementSegment, OwnerAgreement
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from finance.models import ExchangeRate, Payment, RentCoverageAllocation
from marketplace.models import Booking, BookingQuote, Listing, PaymentCheckout, ProviderEvent
from marketplace.services.payments import payment_provider_registry
from marketplace.services.payments.providers.base import PaymentProviderError
from notification.services.notifications import notify
from property.models import Property

from core.constants import (
    BookingStatus,
    LeaseStatus,
    ListingStatus,
    NotificationAudience,
    NotificationType,
    OwnerAgreementStatus,
    PaymentCheckoutStatus,
    PaymentKind,
    PaymentStatus,
    PropertyEngagementType,
    UserRole,
)

logger = logging.getLogger(__name__)
MONEY = Decimal("0.01")


class BookingValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AgreementCoverage:
    agreement: OwnerAgreement
    start_date: date
    end_date: date


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def add_months(value: date, months: int) -> date:
    target_month = value.month - 1 + months
    year = value.year + target_month // 12
    month = target_month % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1]))


class BookingService:
    HOLD_DURATION = timedelta(minutes=30)
    QUOTE_DURATION = timedelta(minutes=10)

    @staticmethod
    def enabled_providers() -> list[str]:
        return payment_provider_registry.enabled_codes()

    @classmethod
    def eligibility(cls, listing: Listing) -> dict:
        prop = listing.property
        reason = None
        # Managed listings can remain published while an active lease makes
        # their legacy is_active flag false. Direct-booking availability is
        # date-derived, so that flag must not hide later, non-overlapping stays.
        if listing.deleted_at or listing.status != ListingStatus.PUBLISHED:
            reason = "listing_not_published"
        elif prop.engagement_type != PropertyEngagementType.MANAGED:
            reason = "one_off_listing"
        elif not prop.is_verified:
            reason = "listing_not_verified"
        elif cls._monthly_rent(listing) is None:
            reason = "pricing_unavailable"
        elif not cls.enabled_providers():
            reason = "payments_unavailable"

        chain = cls._agreement_chain(listing)
        if reason is None and not chain:
            reason = "owner_agreement_unavailable"
        earliest = max(timezone.localdate(), chain[0].start_date) if chain else None
        latest = cls._continuous_horizon(chain) if chain else None
        if earliest and latest and earliest > latest:
            reason = reason or "owner_agreement_unavailable"

        return {
            "eligible": reason is None,
            "reason": reason,
            "minimum_stay_months": listing.minimum_stay or 1,
            "earliest_start_date": earliest.isoformat() if earliest else None,
            "latest_end_date": latest.isoformat() if latest else None,
            "blocked_ranges": cls.blocked_ranges(prop),
            "providers": cls.enabled_providers() if reason not in {"payments_unavailable"} else [],
        }

    @classmethod
    def booking_options(cls, listing: Listing) -> dict:
        result = cls.eligibility(listing)
        monthly_rent = cls._monthly_rent(listing)
        deposit = cls._deposit(listing)
        return {
            "listing_id": listing.id,
            **result,
            "monthly_rent": str(monthly_rent) if monthly_rent is not None else None,
            "deposit_amount": str(deposit),
            "currency": listing.currency or listing.property.tenant_charge_currency,
        }

    @classmethod
    def blocked_ranges(cls, prop: Property) -> list[dict]:
        cls.expire_stale_holds(property_id=prop.id)
        lease_ranges = prop.leases.filter(
            status__in=[LeaseStatus.PENDING_SIGNATURE, LeaseStatus.SCHEDULED, LeaseStatus.ACTIVE]
        ).values_list("start_date", "end_date")
        booking_ranges = prop.bookings.filter(
            Q(status=BookingStatus.CONFIRMED)
            | Q(
                status=BookingStatus.PAYMENT_PENDING,
                payment_checkout__status=PaymentCheckoutStatus.PENDING,
                payment_checkout__expires_at__gt=timezone.now(),
            )
        ).values_list("requested_start_date", "requested_end_date")
        ranges = sorted([*lease_ranges, *booking_ranges])
        merged: list[list[date]] = []
        for start, end in ranges:
            if merged and start <= merged[-1][1] + timedelta(days=1):
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return [{"start_date": start.isoformat(), "end_date": end.isoformat()} for start, end in merged]

    @classmethod
    def create_quote(cls, *, listing: Listing, tenant, start_date: date, end_date: date) -> BookingQuote:
        eligibility = cls.eligibility(listing)
        if not eligibility["eligible"]:
            raise BookingValidationError(eligibility["reason"] or "listing_not_bookable")
        if start_date < timezone.localdate() or end_date < start_date:
            raise BookingValidationError("invalid_booking_dates")
        minimum_end = add_months(start_date, listing.minimum_stay or 1) - timedelta(days=1)
        if end_date < minimum_end:
            raise BookingValidationError("minimum_stay_not_met")
        coverage = cls.agreement_coverage(listing, start_date, end_date)
        if cls.has_conflict(listing.property, start_date, end_date):
            raise BookingValidationError("dates_unavailable")

        monthly_rent = cls._monthly_rent(listing)
        if monthly_rent is None:
            raise BookingValidationError("pricing_unavailable")
        periods = cls.price_periods(start_date, end_date, monthly_rent)
        deposit = cls._deposit(listing)
        first_rent = Decimal(periods[0]["amount"])
        full_rent = money(sum((Decimal(period["amount"]) for period in periods), Decimal("0")))
        currency = listing.currency or listing.property.tenant_charge_currency
        rate = ExchangeRate.objects.filter(currency=currency, effective_date__lte=timezone.localdate()).first()
        return BookingQuote.objects.create(
            listing=listing,
            tenant=tenant,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            monthly_rent=monthly_rent,
            deposit_amount=deposit,
            first_period_rent=first_rent,
            full_stay_rent=full_rent,
            first_month_total=money(deposit + first_rent),
            full_stay_total=money(deposit + full_rent),
            periods=periods,
            agreement_ids=[item.agreement.id for item in coverage],
            fx_rate=rate.rate if rate else None,
            expires_at=timezone.now() + cls.QUOTE_DURATION,
        )

    @classmethod
    @transaction.atomic
    def create_checkout(
        cls, *, quote: BookingQuote, tenant, provider: str, pay_full_stay: bool, idempotency_key: str
    ) -> PaymentCheckout:
        existing = PaymentCheckout.objects.filter(tenant=tenant, idempotency_key=idempotency_key).first()
        if existing:
            return existing
        if quote.tenant_id != tenant.id or quote.expires_at <= timezone.now():
            raise BookingValidationError("quote_expired")
        if provider not in cls.enabled_providers():
            raise BookingValidationError("provider_unavailable")

        Property.objects.select_for_update().get(pk=quote.listing.property_id)
        cls.expire_stale_holds(property_id=quote.listing.property_id)
        if cls.has_conflict(quote.listing.property, quote.start_date, quote.end_date):
            raise BookingValidationError("dates_unavailable")
        cls.agreement_coverage(quote.listing, quote.start_date, quote.end_date)

        booking = Booking.objects.create(
            listing=quote.listing,
            property=quote.listing.property,
            tenant=tenant,
            requested_start_date=quote.start_date,
            requested_end_date=quote.end_date,
            monthly_rent_offer=quote.monthly_rent,
            status=BookingStatus.PAYMENT_PENDING,
        )
        original_amount = quote.full_stay_total if pay_full_stay else quote.first_month_total
        provider_adapter = payment_provider_registry.get(provider)
        try:
            prepared_amount = provider_adapter.prepare_amount(
                original_amount=original_amount,
                original_currency=quote.currency,
                fx_rate=quote.fx_rate,
                quantize=money,
            )
        except PaymentProviderError as exc:
            raise BookingValidationError(str(exc)) from exc

        checkout = PaymentCheckout.objects.create(
            quote=quote,
            booking=booking,
            tenant=tenant,
            idempotency_key=idempotency_key,
            provider=provider,
            pay_full_stay=pay_full_stay,
            original_amount=original_amount,
            original_currency=quote.currency,
            provider_amount=prepared_amount.amount,
            provider_currency=prepared_amount.currency,
            fx_rate=prepared_amount.fx_rate,
            checkout_url="https://i-deal.uz/payment-return",
            expires_at=timezone.now() + cls.HOLD_DURATION,
        )
        hosted_checkout = provider_adapter.create_hosted_checkout(checkout)
        checkout.checkout_url = hosted_checkout.url
        checkout.external_id = hosted_checkout.external_id
        checkout.save(update_fields=["checkout_url", "external_id", "updated_at"])
        return checkout

    @classmethod
    def has_conflict(cls, prop: Property, start_date: date, end_date: date, *, exclude_booking_id=None) -> bool:
        lease_conflict = prop.leases.filter(
            status__in=[LeaseStatus.PENDING_SIGNATURE, LeaseStatus.SCHEDULED, LeaseStatus.ACTIVE],
            start_date__lte=end_date,
            end_date__gte=start_date,
        ).exists()
        bookings = prop.bookings.filter(
            Q(status=BookingStatus.CONFIRMED)
            | Q(
                status=BookingStatus.PAYMENT_PENDING,
                payment_checkout__status=PaymentCheckoutStatus.PENDING,
                payment_checkout__expires_at__gt=timezone.now(),
            ),
            requested_start_date__lte=end_date,
            requested_end_date__gte=start_date,
        )
        if exclude_booking_id:
            bookings = bookings.exclude(pk=exclude_booking_id)
        return lease_conflict or bookings.exists()

    @classmethod
    def agreement_coverage(cls, listing: Listing, start_date: date, end_date: date) -> list[AgreementCoverage]:
        chain = cls._agreement_chain(listing)
        active = next((item for item in chain if item.start_date <= start_date <= item.end_date), None)
        if active is None:
            raise BookingValidationError("owner_agreement_unavailable")
        currency = listing.currency or listing.property.tenant_charge_currency
        cursor = start_date
        coverage = []
        current = active
        while cursor <= end_date:
            if current.currency != currency or current.status == OwnerAgreementStatus.TERMINATED:
                raise BookingValidationError("owner_agreement_currency_mismatch")
            covered_end = min(end_date, current.end_date)
            coverage.append(AgreementCoverage(current, cursor, covered_end))
            cursor = covered_end + timedelta(days=1)
            if cursor > end_date:
                break
            try:
                renewed = current.renewed_agreement
            except OwnerAgreement.DoesNotExist as exc:
                raise BookingValidationError("owner_agreement_gap") from exc
            if renewed.start_date != cursor:
                raise BookingValidationError("owner_agreement_gap")
            current = renewed
        return coverage

    @classmethod
    def price_periods(cls, start_date: date, end_date: date, monthly_rent: Decimal) -> list[dict]:
        periods = []
        cursor = start_date
        while cursor <= end_date:
            anniversary_end = add_months(cursor, 1) - timedelta(days=1)
            period_end = min(anniversary_end, end_date)
            full_days = (anniversary_end - cursor).days + 1
            occupied_days = (period_end - cursor).days + 1
            amount = money(monthly_rent if period_end == anniversary_end else monthly_rent * occupied_days / full_days)
            periods.append({"start_date": cursor.isoformat(), "end_date": period_end.isoformat(), "amount": str(amount)})
            cursor = period_end + timedelta(days=1)
        return periods

    @classmethod
    @transaction.atomic
    def fulfill_checkout(
        cls,
        *,
        checkout_id: int,
        external_event_id: str,
        event_type: str,
        payload: dict,
        succeeded: bool,
        external_id: str | None = None,
    ) -> PaymentCheckout:
        checkout = PaymentCheckout.objects.select_for_update().select_related("booking", "quote__listing__property").get(
            pk=checkout_id
        )
        try:
            # The savepoint keeps a duplicate-event IntegrityError from
            # poisoning the surrounding fulfillment transaction.
            with transaction.atomic():
                event = ProviderEvent.objects.create(
                    checkout=checkout,
                    provider=checkout.provider,
                    external_event_id=external_event_id,
                    event_type=event_type,
                    payload=payload,
                )
        except IntegrityError:
            return PaymentCheckout.objects.get(pk=checkout_id)
        if checkout.status == PaymentCheckoutStatus.SUCCEEDED:
            event.result = {"status": checkout.status, "duplicate": True}
            event.save(update_fields=["result", "updated_at"])
            return checkout
        if not succeeded:
            checkout.status = PaymentCheckoutStatus.FAILED
            checkout.booking.status = BookingStatus.PAYMENT_FAILED
            checkout.booking.save(update_fields=["status", "updated_at"])
            checkout.save(update_fields=["status", "updated_at"])
            event.result = {"status": checkout.status}
            event.save(update_fields=["result", "updated_at"])
            return checkout

        Property.objects.select_for_update().get(pk=checkout.booking.property_id)
        if cls.has_conflict(
            checkout.booking.property,
            checkout.booking.requested_start_date,
            checkout.booking.requested_end_date,
            exclude_booking_id=checkout.booking_id,
        ):
            checkout.status = PaymentCheckoutStatus.RECONCILIATION_REQUIRED
            checkout.booking.status = BookingStatus.RECONCILIATION_REQUIRED
            logger.error("Paid checkout %s conflicts with occupied inventory; manual refund required", checkout.id)
            cls._notify_reconciliation(checkout)
        else:
            cls._fulfill_booking(checkout)
            checkout.status = PaymentCheckoutStatus.SUCCEEDED
            checkout.booking.status = BookingStatus.CONFIRMED
        checkout.external_id = external_id or checkout.external_id
        checkout.completed_at = timezone.now()
        checkout.booking.save(update_fields=["status", "converted_lease", "updated_at"])
        checkout.save(update_fields=["status", "external_id", "completed_at", "updated_at"])
        event.result = {"status": checkout.status}
        event.save(update_fields=["result", "updated_at"])
        return checkout

    @staticmethod
    def _notify_reconciliation(checkout: PaymentCheckout) -> None:
        from account.models import User

        for recipient in User.objects.filter(role=UserRole.MANAGEMENT, is_active=True):
            notify(
                recipient=recipient,
                type=NotificationType.GENERAL,
                audience=NotificationAudience.ERP,
                title=_("Paid booking requires reconciliation"),
                body=_("Checkout %(checkout_id)s was paid after its date range became unavailable. Review and refund manually.")
                % {"checkout_id": checkout.id},
                related_object_type="payment_checkout",
                related_object_id=checkout.id,
            )

    @classmethod
    def _fulfill_booking(cls, checkout: PaymentCheckout) -> None:
        quote = checkout.quote
        coverage = cls.agreement_coverage(quote.listing, quote.start_date, quote.end_date)
        lease = Lease.objects.create(
            property=quote.listing.property,
            owner_agreement=coverage[0].agreement,
            tenant=checkout.tenant,
            start_date=quote.start_date,
            end_date=quote.end_date,
            monthly_rent=quote.monthly_rent,
            deposit=quote.deposit_amount,
            status=LeaseStatus.PENDING_SIGNATURE,
        )
        LeaseAgreementSegment.objects.bulk_create(
            [
                LeaseAgreementSegment(
                    lease=lease,
                    owner_agreement=item.agreement,
                    start_date=item.start_date,
                    end_date=item.end_date,
                )
                for item in coverage
            ]
        )
        checkout.booking.converted_lease = lease
        deposit = Payment.objects.create(
            checkout=checkout,
            lease=lease,
            tenant=checkout.tenant,
            paid_by=checkout.tenant,
            amount=quote.deposit_amount,
            currency=quote.currency,
            payment_date=timezone.localdate(),
            due_date=quote.start_date,
            kind=PaymentKind.DEPOSIT,
            status=PaymentStatus.PENDING,
            method=checkout.provider,
            gateway_ref=checkout.external_id,
        )
        deposit.status = PaymentStatus.PAID
        deposit.save(update_fields=["status", "updated_at"])
        for index, period in enumerate(quote.periods):
            paid = checkout.pay_full_stay or index == 0
            payment = Payment.objects.create(
                checkout=checkout,
                lease=lease,
                tenant=checkout.tenant,
                paid_by=checkout.tenant,
                amount=Decimal(period["amount"]),
                currency=quote.currency,
                payment_date=timezone.localdate(),
                due_date=date.fromisoformat(period["start_date"]),
                rental_period=date.fromisoformat(period["start_date"]),
                kind=PaymentKind.RENT,
                status=PaymentStatus.PENDING,
                method=checkout.provider,
                gateway_ref=checkout.external_id if paid else None,
            )
            cls._create_coverage_allocations(payment, coverage)
            if paid:
                payment.status = PaymentStatus.PAID
                payment.save(update_fields=["status", "updated_at"])

    @classmethod
    def _create_coverage_allocations(cls, payment: Payment, coverage: list[AgreementCoverage]) -> None:
        period_start = payment.rental_period
        next_payment_start = add_months(period_start, 1)
        period_end = min(payment.lease.end_date, next_payment_start - timedelta(days=1))
        slices = []
        cursor = period_start
        while cursor <= period_end:
            agreement_part = next(item for item in coverage if item.start_date <= cursor <= item.end_date)
            month_end = cursor.replace(day=calendar.monthrange(cursor.year, cursor.month)[1])
            slice_end = min(period_end, agreement_part.end_date, month_end)
            slices.append((agreement_part.agreement, cursor, slice_end))
            cursor = slice_end + timedelta(days=1)
        total_days = (period_end - period_start).days + 1
        allocated = Decimal("0")
        for index, (agreement, start, end) in enumerate(slices):
            amount = (
                payment.amount - allocated
                if index == len(slices) - 1
                else money(payment.amount * ((end - start).days + 1) / total_days)
            )
            RentCoverageAllocation.objects.create(
                payment=payment, owner_agreement=agreement, start_date=start, end_date=end, amount=amount
            )
            allocated += amount

    @classmethod
    def expire_stale_holds(cls, *, property_id: int | None = None) -> int:
        qs = PaymentCheckout.objects.filter(status=PaymentCheckoutStatus.PENDING, expires_at__lte=timezone.now())
        if property_id is not None:
            qs = qs.filter(booking__property_id=property_id)
        ids = list(qs.values_list("id", flat=True))
        if not ids:
            return 0
        PaymentCheckout.objects.filter(id__in=ids).update(status=PaymentCheckoutStatus.EXPIRED)
        Booking.objects.filter(payment_checkout__id__in=ids, status=BookingStatus.PAYMENT_PENDING).update(
            status=BookingStatus.PAYMENT_EXPIRED
        )
        return len(ids)

    @staticmethod
    def _monthly_rent(listing: Listing) -> Decimal | None:
        value = listing.monthly_price or listing.listed_price or listing.property.tenant_charge_price
        return money(value) if value is not None else None

    @classmethod
    def _deposit(cls, listing: Listing) -> Decimal:
        value = listing.deposit_amount
        if value is None:
            value = listing.property.deposit_amount
        if value is None:
            value = cls._monthly_rent(listing) or Decimal("0")
        return money(value)

    @staticmethod
    def _agreement_chain(listing: Listing) -> list[OwnerAgreement]:
        agreements = list(
            OwnerAgreement.objects.filter(property=listing.property)
            .exclude(status=OwnerAgreementStatus.TERMINATED)
            .order_by("start_date", "id")
        )
        if not agreements:
            return []
        current = listing.owner_agreement
        if current is None:
            current = next((item for item in agreements if item.previous_agreement_id is None), agreements[0])
        chain = [current]
        seen = {current.id}
        while True:
            next_item = next((item for item in agreements if item.previous_agreement_id == current.id), None)
            if next_item is None or next_item.id in seen:
                break
            chain.append(next_item)
            seen.add(next_item.id)
            current = next_item
        return chain

    @staticmethod
    def _continuous_horizon(chain: list[OwnerAgreement]) -> date:
        currency = chain[0].currency
        horizon = chain[0].end_date
        for previous, current in zip(chain, chain[1:], strict=False):
            if current.start_date != previous.end_date + timedelta(days=1) or current.currency != currency:
                break
            horizon = current.end_date
        return horizon

def provider_timestamp(milliseconds: int) -> datetime:
    return datetime.combine(date.fromtimestamp(milliseconds / 1000), time.min, tzinfo=timezone.get_current_timezone())
