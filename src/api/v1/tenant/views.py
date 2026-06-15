from django.utils.translation import gettext_lazy as _
from dmr import Body, Query

from api.v1.tenant.schemas import (
    TenantPaymentOutput,
    TenantServiceRequestCreateInput,
)
from core.api.permissions import RoleAuth
from core.api.views import BaseController, ListQuery
from core.constants import LeaseStatus, UserRole


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


def _build_service_request_output(sr):
    return {
        "id": sr.id,
        "property_id": sr.property_id,
        "property_name": sr.property.name,
        "title": sr.title,
        "description": sr.description,
        "priority": sr.priority,
        "status": sr.status,
        "cost": str(sr.cost) if sr.cost else None,
        "resolution_notes": sr.resolution_notes,
        "created_at": sr.created_at.isoformat(),
        "updated_at": sr.updated_at.isoformat(),
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
        return self.ok(items)

    def post(self) -> dict:
        return self.ok({"message": str(_("Online payment coming soon. Please contact management."))})


class TenantServiceRequestListCreateView(BaseController):
    auth = (RoleAuth(UserRole.TENANT),)

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        from maintenance.models import ServiceRequest

        qs = ServiceRequest.objects.filter(tenant=user).select_related("property").order_by("-created_at")
        items = [_build_service_request_output(obj) for obj in qs]
        return self.ok(items)

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
        return self.ok(_build_service_request_output(sr))
