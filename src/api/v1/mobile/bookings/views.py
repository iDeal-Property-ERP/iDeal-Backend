from http import HTTPStatus

from django.shortcuts import get_object_or_404
from dmr import Body, Path
from marketplace.models import Booking, BookingQuote, Listing
from marketplace.services.booking import BookingService, BookingValidationError
from marketplace.services.listings import ordered_photos, photo_url, photo_variant_url

from api.v1.mobile.bookings.schemas import BookingCheckoutInput, BookingDetailPath, BookingQuoteInput
from core.api.views import BaseController


def serialize_quote(quote: BookingQuote) -> dict:
    return {
        "id": quote.id,
        "listing_id": quote.listing_id,
        "start_date": quote.start_date.isoformat(),
        "end_date": quote.end_date.isoformat(),
        "currency": quote.currency,
        "monthly_rent": str(quote.monthly_rent),
        "deposit_amount": str(quote.deposit_amount),
        "periods": quote.periods,
        "options": {
            "first_month": {
                "rent_amount": str(quote.first_period_rent),
                "total_amount": str(quote.first_month_total),
            },
            "full_stay": {
                "rent_amount": str(quote.full_stay_rent),
                "total_amount": str(quote.full_stay_total),
            },
        },
        "expires_at": quote.expires_at.isoformat(),
    }


def serialize_checkout(checkout) -> dict:
    return {
        "booking_id": checkout.booking_id,
        "checkout_id": checkout.id,
        "public_token": str(checkout.public_token),
        "provider": checkout.provider,
        "status": checkout.status,
        "checkout_url": checkout.checkout_url,
        "expires_at": checkout.expires_at.isoformat(),
    }


def serialize_booking(booking: Booking, request) -> dict:
    listing = booking.listing
    photos = ordered_photos(listing.property)
    cover_photo = photos[0] if photos else None
    checkout = getattr(booking, "payment_checkout", None)
    lease = booking.converted_lease
    return {
        "id": booking.id,
        "listing": {
            "id": listing.id,
            "title": listing.property.name,
            "address": listing.property.address,
            "cover_image_url": photo_url(cover_photo, request) if cover_photo else None,
            "cover_preview_url": photo_variant_url(cover_photo, "preview_image", request) if cover_photo else None,
            "cover_display_url": photo_variant_url(cover_photo, "display_image", request) if cover_photo else None,
        },
        "start_date": booking.requested_start_date.isoformat(),
        "end_date": booking.requested_end_date.isoformat(),
        "status": booking.status,
        "amount": str(checkout.original_amount) if checkout else None,
        "currency": checkout.original_currency if checkout else listing.currency,
        "pay_full_stay": checkout.pay_full_stay if checkout else False,
        "created_at": booking.created_at.isoformat(),
        "lease": {"id": lease.id, "status": lease.status} if lease else None,
        "checkout": serialize_checkout(checkout) if checkout else None,
    }


class MobileBookingQuoteView(BaseController):
    def post(self, parsed_body: Body[BookingQuoteInput]) -> dict:
        listing = get_object_or_404(
            Listing.objects.select_related("property", "owner_agreement"), pk=parsed_body.listing_id
        )
        try:
            quote = BookingService.create_quote(
                listing=listing,
                tenant=self.request.user,
                start_date=parsed_body.start_date,
                end_date=parsed_body.end_date,
            )
        except BookingValidationError as exc:
            return self.fail(error=str(exc))
        return self.ok(serialize_quote(quote))


class MobileBookingCheckoutView(BaseController):
    def post(self, parsed_body: Body[BookingCheckoutInput]) -> dict:
        idempotency_key = self.request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key:
            return self.fail(error="idempotency_key_required")
        quote = get_object_or_404(BookingQuote.objects.select_related("listing__property"), pk=parsed_body.quote_id)
        try:
            checkout = BookingService.create_checkout(
                quote=quote,
                tenant=self.request.user,
                provider=parsed_body.provider,
                pay_full_stay=parsed_body.pay_full_stay,
                idempotency_key=idempotency_key,
            )
        except BookingValidationError as exc:
            return self.fail(error=str(exc), status_code=HTTPStatus.CONFLICT)
        return self.ok(serialize_checkout(checkout))


class MobileBookingListView(BaseController):
    def get(self) -> dict:
        bookings = (
            Booking.objects.filter(tenant=self.request.user)
            .select_related("listing__property", "converted_lease", "payment_checkout")
            .prefetch_related("listing__property__photos")
            .order_by("-created_at")
        )
        return self.ok([serialize_booking(booking, self.request) for booking in bookings])


class MobileBookingDetailView(BaseController):
    def get(self, parsed_path: Path[BookingDetailPath]) -> dict:
        booking = get_object_or_404(
            Booking.objects.filter(tenant=self.request.user)
            .select_related("listing__property", "converted_lease", "payment_checkout")
            .prefetch_related("listing__property__photos"),
            pk=parsed_path.pk,
        )
        BookingService.expire_stale_holds(property_id=booking.property_id)
        booking.refresh_from_db()
        return self.ok(serialize_booking(booking, self.request))
