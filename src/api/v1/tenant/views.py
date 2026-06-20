from datetime import date as date_type
from http import HTTPStatus

from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query

from api.v1.tenant.schemas import (
    TenantBookingCreateInput,
    TenantBookingOutput,
    TenantPaymentCreateInput,
    TenantPaymentOutput,
    TenantServiceRequestCreateInput,
    TenantServiceRequestOutput,
)
from api.v1.vas.schemas import TenantServiceOrderCreateInput
from core.api.permissions import RoleAuth
from core.api.views import BaseController, DetailPath, GenericController, ListQuery
from core.constants import BookingStatus, LeaseStatus, PaymentStatus, UserRole
from core.utils.pagination import build_paginated_response


def _build_lease_output(lease):
    from finance.models import Payment

    next_payment = Payment.objects.filter(lease=lease, status="pending").order_by("due_date").first()
    return {
        "lease_id": lease.id,
        "property_id": lease.property_id,
        "property_name": lease.property.name,
        "property_address": lease.property.address,
        "start_date": lease.start_date.isoformat(),
        "end_date": lease.end_date.isoformat(),
        "monthly_rent": str(lease.monthly_rent),
        "deposit": str(lease.deposit),
        "status": lease.status,
        "next_payment_due": next_payment.due_date.isoformat() if next_payment else lease.end_date.isoformat(),
        "rent_due": str(next_payment.amount) if next_payment else str(lease.monthly_rent),
    }


class TenantHomeView(BaseController):
    auth = (RoleAuth(UserRole.TENANT),)

    def get(self) -> dict:
        user = self.request.user
        from contract.models import Lease

        lease = Lease.objects.filter(tenant=user, status=LeaseStatus.ACTIVE).select_related("property").first()
        if not lease:
            return self.ok(
                {
                    "lease_id": None,
                    "property_id": None,
                    "property_name": None,
                    "property_address": None,
                    "start_date": None,
                    "end_date": None,
                    "monthly_rent": None,
                    "deposit": None,
                    "status": None,
                    "next_payment_due": None,
                    "rent_due": None,
                }
            )
        return self.ok(_build_lease_output(lease))


class TenantPaymentListCreateView(BaseController):
    auth = (RoleAuth(UserRole.TENANT),)

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        from finance.models import Payment

        qs = Payment.objects.filter(tenant=user).order_by("-payment_date")
        items = [TenantPaymentOutput.model_validate(obj).model_dump(mode="json") for obj in qs]
        if parsed_query.page is not None:
            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)

    def post(self, parsed_body: Body[TenantPaymentCreateInput]) -> dict:
        user = self.request.user
        from contract.models import Lease

        lease = (
            Lease.objects.filter(tenant=user, status=LeaseStatus.ACTIVE)
            .select_related("property")
            .order_by("-start_date")
            .first()
        )
        if not lease:
            return self.fail(
                error=str(_("You do not have an active lease to pay for")),
                status_code=400,
            )

        from finance.models import Payment

        amount = parsed_body.amount if parsed_body.amount is not None else lease.monthly_rent
        # Manual initiation: the payment starts PENDING and management confirms it.
        # TODO: when an online gateway (Click / Payme / Uzum) is wired, method=online
        # would hand off to the gateway and the callback would flip status to PAID.
        payment = Payment.objects.create(
            lease=lease,
            tenant=user,
            paid_by=user,
            amount=amount,
            currency=lease.property.tenant_charge_currency,
            payment_date=date_type.today(),
            due_date=date_type.today(),
            status=PaymentStatus.PENDING,
            method=parsed_body.method,
            notes=parsed_body.notes,
        )
        return self.ok(TenantPaymentOutput.model_validate(payment).model_dump(mode="json"))


class TenantServiceRequestListCreateView(GenericController):
    auth = (RoleAuth(UserRole.TENANT),)
    output_schema = TenantServiceRequestOutput

    def get_queryset(self):
        from maintenance.models import ServiceRequest

        user = self.request.user
        return ServiceRequest.objects.filter(tenant=user).select_related("property").order_by("-created_at")

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return self.list_response(self.get_queryset(), parsed_query)

    def post(self, parsed_body: Body[TenantServiceRequestCreateInput]) -> dict:
        user = self.request.user

        from contract.models import Lease

        has_active = Lease.objects.filter(
            tenant=user,
            property_id=parsed_body.property_id,
            status=LeaseStatus.ACTIVE,
        ).exists()
        if not has_active:
            return self.fail(
                error=str(_("You can only submit requests for properties you currently rent")),
                status_code=403,
            )
        from maintenance.models import ServiceRequest

        sr = ServiceRequest.objects.create(
            property_id=parsed_body.property_id,
            tenant=user,
            title=parsed_body.title,
            description=parsed_body.description,
            priority=parsed_body.priority,
        )
        return self.ok(self.to_output(sr))


class TenantBookingListCreateView(BaseController):
    auth = (RoleAuth(UserRole.TENANT),)

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        from marketplace.models import Booking

        qs = Booking.objects.filter(tenant=self.request.user).select_related("property").order_by("-created_at")
        items = [TenantBookingOutput.model_validate(obj).model_dump(mode="json") for obj in qs]
        if parsed_query.page is not None:
            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)

    def post(self, parsed_body: Body[TenantBookingCreateInput]) -> dict:
        from marketplace.models import Booking, Listing

        listing = Listing.objects.filter(pk=parsed_body.listing_id, is_active=True).select_related("property").first()
        if listing is None:
            return self.fail(error=str(_("Listing is not available")), status_code=HTTPStatus.NOT_FOUND)

        booking = Booking.objects.create(
            listing=listing,
            property=listing.property,
            tenant=self.request.user,
            requested_start_date=parsed_body.requested_start_date,
            requested_end_date=parsed_body.requested_end_date,
            monthly_rent_offer=parsed_body.monthly_rent_offer,
            message=parsed_body.message,
        )
        return self.ok(TenantBookingOutput.model_validate(booking).model_dump(mode="json"))


class TenantVASOrderListCreateView(BaseController):
    auth = (RoleAuth(UserRole.TENANT),)

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        from vas.models import ServiceOrder

        from api.v1.vas.schemas import ServiceOrderOutput

        qs = (
            ServiceOrder.objects.filter(tenant=self.request.user).select_related("catalog_item").order_by("-created_at")
        )
        items = [ServiceOrderOutput.model_validate(obj).model_dump(mode="json") for obj in qs]
        if parsed_query.page is not None:
            return self.ok(build_paginated_response(items, parsed_query.page, parsed_query.per_page))
        return self.ok(items)

    def post(self, parsed_body: Body[TenantServiceOrderCreateInput]) -> dict:
        from contract.models import Lease
        from vas.models import ServiceCatalogItem, ServiceOrder

        from api.v1.vas.schemas import ServiceOrderOutput

        user = self.request.user
        lease = (
            Lease.objects.filter(tenant=user, status=LeaseStatus.ACTIVE)
            .select_related("property")
            .order_by("-start_date")
            .first()
        )
        if not lease:
            return self.fail(
                error=str(_("You need an active lease to order a service")),
                status_code=400,
            )

        item = ServiceCatalogItem.objects.filter(pk=parsed_body.catalog_item_id, is_active=True).first()
        if item is None:
            return self.fail(error=str(_("Service is not available")), status_code=HTTPStatus.NOT_FOUND)

        order = ServiceOrder.objects.create(
            catalog_item=item,
            tenant=user,
            property=lease.property,
            lease=lease,
            cost=item.base_price,
            currency=item.currency,
            scheduled_for=parsed_body.scheduled_for,
            notes=parsed_body.notes,
        )
        return self.ok(ServiceOrderOutput.model_validate(order).model_dump(mode="json"))


class TenantBookingCancelView(BaseController):
    auth = (RoleAuth(UserRole.TENANT),)

    def post(self, parsed_path: Path[DetailPath]) -> dict:
        from marketplace.models import Booking

        booking = Booking.objects.filter(pk=parsed_path.pk, tenant=self.request.user).select_related("property").first()
        if booking is None:
            return self.fail(error=str(_("Booking not found")), status_code=HTTPStatus.NOT_FOUND)
        if booking.status in (BookingStatus.CONVERTED, BookingStatus.CANCELLED):
            return self.fail(
                error=str(_("This booking can no longer be cancelled")),
                message=str(_("Invalid status transition")),
            )
        booking.status = BookingStatus.CANCELLED
        booking.save(update_fields=["status", "updated_at"])
        return self.ok(
            TenantBookingOutput.model_validate(booking).model_dump(mode="json"),
            status_code=HTTPStatus.OK,
        )
