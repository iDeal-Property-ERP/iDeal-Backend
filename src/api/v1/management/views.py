from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query

from api.v1.management.schemas import ManagementUserUpdateInput
from core.api.views import BaseController, DetailPath, ListQuery
from core.constants import UserRole


def _ensure_management(user):
    return user.role == UserRole.MANAGEMENT


def _build_user_output(u):
    return {
        "id": u.id,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "patronymic": u.patronymic,
        "username": u.username,
        "phone": u.phone,
        "email": u.email,
        "role": u.role,
        "is_active": u.is_active,
        "is_verified": u.is_verified,
        "nationality": u.nationality,
        "is_staff": u.is_staff,
        "is_superuser": u.is_superuser,
        "created_at": u.created_at.isoformat(),
        "updated_at": u.updated_at.isoformat(),
    }


def _build_property_output(p):
    return {
        "id": p.id,
        "name": p.name,
        "address": p.address,
        "district_id": p.district_id,
        "district_name": p.district.name,
        "rooms": p.rooms,
        "area_sqm": p.area_sqm,
        "floor": p.floor,
        "total_floors": p.total_floors,
        "owner_id": p.owner_id,
        "owner_name": f"{p.owner.first_name} {p.owner.last_name or ''}".strip(),
        "status": p.status,
        "tariff": p.tariff,
        "ask_price": str(p.ask_price),
        "ask_currency": p.ask_currency,
        "owner_guaranteed_price": str(p.owner_guaranteed_price),
        "tenant_charge_price": str(p.tenant_charge_price),
        "vacant_since": p.vacant_since.isoformat() if p.vacant_since else None,
        "vacant_days": p.vacant_days,
        "description": p.description,
        "score": str(p.score),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _build_lease_output(lease_obj):
    return {
        "id": lease_obj.id,
        "property_id": lease_obj.property_id,
        "property_name": lease_obj.property.name,
        "tenant_id": lease_obj.tenant_id,
        "tenant_name": f"{lease_obj.tenant.first_name} {lease_obj.tenant.last_name or ''}".strip(),
        "owner_agreement_id": lease_obj.owner_agreement_id,
        "start_date": lease_obj.start_date.isoformat(),
        "end_date": lease_obj.end_date.isoformat(),
        "monthly_rent": str(lease_obj.monthly_rent),
        "deposit": str(lease_obj.deposit),
        "status": lease_obj.status,
        "created_at": lease_obj.created_at.isoformat(),
        "updated_at": lease_obj.updated_at.isoformat(),
    }


def _build_agreement_output(a):
    return {
        "id": a.id,
        "agreement_number": a.agreement_number,
        "owner_id": a.owner_id,
        "owner_name": f"{a.owner.first_name} {a.owner.last_name or ''}".strip(),
        "property_id": a.property_id,
        "property_name": a.property.name,
        "signed_date": a.signed_date.isoformat(),
        "start_date": a.start_date.isoformat(),
        "end_date": a.end_date.isoformat(),
        "status": a.status,
        "commission_rate": str(a.commission_rate),
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
    }


def _build_payment_output(pay):
    return {
        "id": pay.id,
        "lease_id": pay.lease_id,
        "tenant_id": pay.tenant_id,
        "tenant_name": f"{pay.tenant.first_name} {pay.tenant.last_name or ''}".strip(),
        "paid_by_id": pay.paid_by_id,
        "amount": str(pay.amount),
        "currency": pay.currency,
        "payment_date": pay.payment_date.isoformat(),
        "due_date": pay.due_date.isoformat(),
        "status": pay.status,
        "method": pay.method,
        "notes": pay.notes,
        "created_at": pay.created_at.isoformat(),
    }


def _build_payout_output(po):
    return {
        "id": po.id,
        "owner_agreement_id": po.owner_agreement_id,
        "owner_id": po.owner_id,
        "owner_name": f"{po.owner.first_name} {po.owner.last_name or ''}".strip(),
        "amount": str(po.amount),
        "currency": po.currency,
        "scheduled_date": po.scheduled_date.isoformat(),
        "paid_date": po.paid_date.isoformat() if po.paid_date else None,
        "status": po.status,
        "created_at": po.created_at.isoformat(),
    }


def _build_service_request_output(sr):
    return {
        "id": sr.id,
        "property_id": sr.property_id,
        "property_name": sr.property.name,
        "tenant_id": sr.tenant_id,
        "tenant_name": f"{sr.tenant.first_name} {sr.tenant.last_name or ''}".strip(),
        "assigned_to_id": sr.assigned_to_id,
        "assigned_to_name": f"{sr.assigned_to.first_name} {sr.assigned_to.last_name or ''}".strip()
        if sr.assigned_to
        else None,
        "title": sr.title,
        "description": sr.description,
        "priority": sr.priority,
        "status": sr.status,
        "cost": str(sr.cost) if sr.cost else None,
        "resolution_notes": sr.resolution_notes,
        "created_at": sr.created_at.isoformat(),
        "updated_at": sr.updated_at.isoformat(),
    }


class DashboardView(BaseController):
    def get(self) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)
        from account.models import User
        from contract.models import Lease, OwnerAgreement
        from finance.models import Payment, PayoutSchedule
        from maintenance.models import ServiceRequest
        from property.models import Property

        users_by_role = User.objects.values("role").annotate(count=Count("id"))
        props_by_status = Property.objects.values("status").annotate(count=Count("id"))
        revenue = Payment.objects.filter(status="paid").aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        pending_payouts = PayoutSchedule.objects.filter(status="scheduled").aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")

        return self.ok(
            {
                "users": {entry["role"]: entry["count"] for entry in users_by_role},
                "properties": {entry["status"]: entry["count"] for entry in props_by_status},
                "active_leases": Lease.objects.filter(status="active").count(),
                "active_agreements": OwnerAgreement.objects.filter(status="active").count(),
                "revenue_collected": str(revenue),
                "pending_payouts": str(pending_payouts),
                "open_service_requests": ServiceRequest.objects.exclude(status="resolved")
                .exclude(status="cancelled")
                .count(),
            }
        )


class ManagementUserListView(BaseController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)
        from account.models import User

        qs = User.objects.all().order_by("-created_at")
        role = self.request.GET.get("role")
        is_active = self.request.GET.get("is_active")
        is_verified = self.request.GET.get("is_verified")
        search = self.request.GET.get("search")

        if role:
            qs = qs.filter(role=role)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        if is_verified is not None:
            qs = qs.filter(is_verified=is_verified.lower() == "true")
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )

        items = [_build_user_output(obj) for obj in qs]
        paginated = _paginate(items, parsed_query)
        return self.ok(paginated)


class ManagementUserDetailUpdateView(BaseController):
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementUserUpdateInput]) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)

        instance = self._get_user(parsed_path.pk)
        data = parsed_body.model_dump(exclude_unset=True)
        for attr, value in data.items():
            setattr(instance, attr, value)
        instance.save()
        return self.ok(_build_user_output(instance))

    @staticmethod
    def _get_user(pk):
        from account.models import User
        from django.shortcuts import get_object_or_404

        return get_object_or_404(User, pk=pk)


class ManagementPropertyListView(BaseController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)
        from property.models import Property

        qs = Property.objects.select_related("district", "owner").order_by("-created_at")
        status = self.request.GET.get("status")
        district_id = self.request.GET.get("district_id")
        tariff = self.request.GET.get("tariff")
        search = self.request.GET.get("search")

        if status:
            qs = qs.filter(status=status)
        if district_id:
            qs = qs.filter(district_id=district_id)
        if tariff:
            qs = qs.filter(tariff=tariff)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(address__icontains=search))

        items = [_build_property_output(obj) for obj in qs]
        paginated = _paginate(items, parsed_query)
        return self.ok(paginated)


class LeaseListView(BaseController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)
        from contract.models import Lease

        qs = Lease.objects.select_related("property", "tenant").order_by("-created_at")
        status = self.request.GET.get("status")
        property_id = self.request.GET.get("property_id")
        tenant_id = self.request.GET.get("tenant_id")

        if status:
            qs = qs.filter(status=status)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)

        items = [_build_lease_output(obj) for obj in qs]
        paginated = _paginate(items, parsed_query)
        return self.ok(paginated)


class OwnerAgreementListView(BaseController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)
        from contract.models import OwnerAgreement

        qs = OwnerAgreement.objects.select_related("owner", "property").order_by("-created_at")
        status = self.request.GET.get("status")
        owner_id = self.request.GET.get("owner_id")
        property_id = self.request.GET.get("property_id")

        if status:
            qs = qs.filter(status=status)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        if property_id:
            qs = qs.filter(property_id=property_id)

        items = [_build_agreement_output(obj) for obj in qs]
        paginated = _paginate(items, parsed_query)
        return self.ok(paginated)


class PaymentListView(BaseController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)
        from finance.models import Payment

        qs = Payment.objects.select_related("tenant").order_by("-payment_date")
        status = self.request.GET.get("status")
        method = self.request.GET.get("method")
        lease_id = self.request.GET.get("lease_id")
        tenant_id = self.request.GET.get("tenant_id")
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")

        if status:
            qs = qs.filter(status=status)
        if method:
            qs = qs.filter(method=method)
        if lease_id:
            qs = qs.filter(lease_id=lease_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if date_from:
            qs = qs.filter(payment_date__gte=date_from)
        if date_to:
            qs = qs.filter(payment_date__lte=date_to)

        items = [_build_payment_output(obj) for obj in qs]
        paginated = _paginate(items, parsed_query)
        return self.ok(paginated)


class PayoutListView(BaseController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)
        from finance.models import PayoutSchedule

        qs = PayoutSchedule.objects.select_related("owner").order_by("-scheduled_date")
        status = self.request.GET.get("status")
        owner_id = self.request.GET.get("owner_id")

        if status:
            qs = qs.filter(status=status)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)

        items = [_build_payout_output(obj) for obj in qs]
        paginated = _paginate(items, parsed_query)
        return self.ok(paginated)


class ManagementServiceRequestListView(BaseController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        if not _ensure_management(user):
            return self.fail(error=str(_("Only management can access this endpoint")), status_code=403)
        from maintenance.models import ServiceRequest

        qs = ServiceRequest.objects.select_related("property", "tenant", "assigned_to").order_by("-created_at")
        status = self.request.GET.get("status")
        priority = self.request.GET.get("priority")
        property_id = self.request.GET.get("property_id")
        tenant_id = self.request.GET.get("tenant_id")

        if status:
            qs = qs.filter(status=status)
        if priority:
            qs = qs.filter(priority=priority)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)

        items = [_build_service_request_output(obj) for obj in qs]
        paginated = _paginate(items, parsed_query)
        return self.ok(paginated)


def _paginate(items, parsed_query):
    from core.utils.pagination import build_paginated_response

    if parsed_query.page is not None:
        return build_paginated_response(items, parsed_query.page, parsed_query.per_page)
    return items
