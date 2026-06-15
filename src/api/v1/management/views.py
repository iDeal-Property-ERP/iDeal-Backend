from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from dmr import Body, Path, Query

from api.v1.management.schemas import (
    DashboardKPIs,
    DashboardOccupancy,
    DashboardOutput,
    GrowthData,
    GrowthPoint,
    InvestorTakeHome,
    KpiNetProfit,
    KpiOccupied,
    KpiPaymentsReceived,
    KpiVacant,
    MaintenanceRequestRow,
    ManagementUserUpdateInput,
    MonthlyPnlRow,
    PnLSummaryCard,
    PnLSummaryOutput,
    RecentPaymentRow,
)
from core.api.permissions import RoleAuth
from core.api.views import BaseController, DetailPath, ListQuery
from core.constants import UserRole


class ManagementView(BaseController):
    auth = (RoleAuth(UserRole.MANAGEMENT),)


def _d(value):
    return str(value.quantize(Decimal("0.01")))


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


class DashboardView(ManagementView):
    def get(self) -> dict:
        user = self.request.user

        today = date.today()

        from contract.models import Lease
        from finance.models import Payment, PayoutSchedule
        from maintenance.models import ServiceRequest
        from property.models import District, Property

        # Greeting / Date / Location
        greeting = f"Xush kelibsiz, {user.first_name} \U0001f44b"
        date_str = today.isoformat()
        first_district = District.objects.values("city").first()
        location = first_district["city"] if first_district else "Toshkent"

        # Overview
        total_properties = Property.objects.count()
        has_overdue = Payment.objects.filter(status="overdue").exists()
        payment_status = "needs_attention" if has_overdue else "good"

        # ---- KPI: Occupied ----
        rented_count = Property.objects.filter(status="rented").count()
        leases_this_month = Lease.objects.filter(
            start_date__year=today.year,
            start_date__month=today.month,
            status="active",
        ).count()

        # ---- KPI: Net profit (this month vs last month) ----
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        def _month_net(year, month):
            inc = (
                Payment.objects.filter(status="paid", payment_date__year=year, payment_date__month=month).aggregate(
                    total=Sum("amount")
                )["total"]
                or Decimal("0.00")
            )
            out = (
                PayoutSchedule.objects.filter(status="paid", paid_date__year=year, paid_date__month=month).aggregate(
                    total=Sum("amount")
                )["total"]
                or Decimal("0.00")
            )
            return inc - out

        net_profit_this = _month_net(today.year, today.month)
        net_profit_last = _month_net(last_month_start.year, last_month_start.month)
        net_profit_change = net_profit_this - net_profit_last

        # ---- KPI: Payments received (last 25 days) ----
        twenty_five_days_ago = today - timedelta(days=25)
        paid_last_25 = Payment.objects.filter(status="paid", payment_date__gte=twenty_five_days_ago)
        payments_amount = paid_last_25.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        payments_total = paid_last_25.count()
        payments_on_time = paid_last_25.filter(payment_date__lte=F("due_date")).count()
        on_time_pct = round(payments_on_time / payments_total * 100) if payments_total > 0 else 100

        # ---- KPI: Vacant units ----
        vacant_count = Property.objects.filter(status="vacant").count()
        vacant_props = list(Property.objects.filter(status="vacant").values_list("tenant_charge_price", flat=True))
        loss_per_day = (
            sum((p / Decimal("30")) for p in vacant_props if p) if vacant_props else Decimal("0.00")
        )

        # ---- Recent Payments ----
        recent_payments_qs = (
            Payment.objects.select_related("tenant", "lease__property")
            .order_by("-payment_date")[:5]
        )
        recent_payments = [
            RecentPaymentRow(
                id=p.id,
                tenant_name=f"{p.tenant.first_name} {p.tenant.last_name or ''}".strip(),
                nationality=p.tenant.nationality,
                property_name=p.lease.property.name,
                amount=_d(p.amount),
                status=p.status,
            )
            for p in recent_payments_qs
        ]

        # ---- Occupancy ----
        props_by_status = {
            entry["status"]: entry["count"]
            for entry in Property.objects.values("status").annotate(count=Count("id"))
        }
        rented = props_by_status.get("rented", 0)
        vacant = props_by_status.get("vacant", 0)
        maintenance = props_by_status.get("maintenance", 0)
        occ_rate = round(rented / total_properties * 100) if total_properties > 0 else 0

        # ---- Maintenance Requests ----
        maint_qs = (
            ServiceRequest.objects.select_related("property", "tenant")
            .filter(status__in=["open", "in_progress"])
            .order_by("-created_at")[:5]
        )
        maintenance_requests = [
            MaintenanceRequestRow(
                id=sr.id,
                title=sr.title,
                property_name=sr.property.name,
                tenant_name=f"{sr.tenant.first_name} {sr.tenant.last_name or ''}".strip(),
                priority=sr.priority,
                status=sr.status,
            )
            for sr in maint_qs
        ]

        output = DashboardOutput(
            greeting=greeting,
            date=date_str,
            location=location,
            total_properties=total_properties,
            payment_status=payment_status,
            kpi=DashboardKPIs(
                occupied=KpiOccupied(value=rented_count, total=total_properties, change=leases_this_month),
                net_profit=KpiNetProfit(value=_d(net_profit_this), change=_d(net_profit_change)),
                payments_received=KpiPaymentsReceived(
                    amount=_d(payments_amount), days=25, on_time_pct=on_time_pct
                ),
                vacant=KpiVacant(value=vacant_count, loss_per_day=_d(loss_per_day)),
            ),
            recent_payments=recent_payments,
            occupancy=DashboardOccupancy(rate=occ_rate, rented=rented, vacant=vacant, maintenance=maintenance),
            maintenance_requests=maintenance_requests,
        )

        return self.ok(output.model_dump(mode="json"))


class PnLSummaryView(ManagementView):
    def get(self) -> dict:
        today = date.today()
        current_year = today.year
        current_month = today.month

        from finance.models import Payment, PayoutSchedule
        from finance.utils import convert_amount
        from property.models import Property

        def _convert(amount, from_currency, to_currency):
            if float(amount) == 0:
                return Decimal("0.00")
            try:
                return convert_amount(amount, from_currency, to_currency)
            except ValueError:
                return Decimal("0.00")

        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        monthly_rows = []
        growth_actual = []
        current_revenue = Decimal("0.00")
        current_owner = Decimal("0.00")
        current_net = Decimal("0.00")
        current_tax = Decimal("0.00")

        for m in range(1, current_month + 1):
            payments = Payment.objects.filter(
                status="paid", payment_date__year=current_year, payment_date__month=m
            )
            payouts = PayoutSchedule.objects.filter(
                status="paid", paid_date__year=current_year, paid_date__month=m
            )

            revenue_uzs = Decimal("0.00")
            for p in payments:
                revenue_uzs += _convert(p.amount, p.currency, "UZS")

            owner_uzs = Decimal("0.00")
            for po in payouts:
                owner_uzs += _convert(po.amount, po.currency, "UZS")

            net_uzs = revenue_uzs - owner_uzs
            tax_uzs = net_uzs * Decimal("0.04")

            revenue_usd = _convert(revenue_uzs, "UZS", "USD")
            owner_usd = _convert(owner_uzs, "UZS", "USD")
            net_usd = _convert(net_uzs, "UZS", "USD")

            monthly_rows.append(
                MonthlyPnlRow(
                    month=month_names[m - 1],
                    revenue=_d(revenue_usd),
                    owner_payouts=_d(owner_usd),
                    profit=_d(net_usd),
                    tax=_d(tax_uzs),
                )
            )
            growth_actual.append(
                GrowthPoint(month=month_names[m - 1], revenue=_d(revenue_usd))
            )

            if m == current_month:
                current_revenue = revenue_usd
                current_owner = owner_usd
                current_net = net_usd
                current_tax = tax_uzs

        summary = PnLSummaryCard(
            gross_revenue=_d(current_revenue),
            owner_payouts=_d(current_owner),
            net_profit=_d(current_net),
            tax=_d(current_tax),
        )

        growth_projected = []
        if len(growth_actual) >= 2:
            last3_revenues = [Decimal(r.revenue) for r in growth_actual[-3:]]
            if last3_revenues[0] > 0:
                avg_growth = sum(
                    (last3_revenues[i + 1] - last3_revenues[i]) / last3_revenues[i]
                    for i in range(len(last3_revenues) - 1)
                ) / (len(last3_revenues) - 1)
                last_rev = last3_revenues[-1]
                for i in range(1, 4):
                    proj_month = current_month + i
                    if proj_month > 12:
                        break
                    last_rev = last_rev * (Decimal("1") + avg_growth)
                    growth_projected.append(
                        GrowthPoint(month=month_names[proj_month - 1], revenue=_d(last_rev))
                    )

        total_properties = Property.objects.count()
        per_property_net = (
            current_net / total_properties if total_properties > 0 else Decimal("0.00")
        )
        investor = InvestorTakeHome(
            monthly=_d(current_net),
            annual=_d(current_net * Decimal("12")),
            property_count=total_properties,
            scaled_50=_d(per_property_net * Decimal("50")),
        )

        output = PnLSummaryOutput(
            summary=summary,
            monthly=monthly_rows,
            growth=GrowthData(actual=growth_actual, projected=growth_projected),
            investor=investor,
        )

        return self.ok(output.model_dump(mode="json"))


class ManagementUserListView(ManagementView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
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


class ManagementUserDetailUpdateView(ManagementView):
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementUserUpdateInput]) -> dict:
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


class ManagementPropertyListView(ManagementView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
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


class LeaseListView(ManagementView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
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


class OwnerAgreementListView(ManagementView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
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


class PaymentListView(ManagementView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
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


class PayoutListView(ManagementView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
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


class ManagementServiceRequestListView(ManagementView):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
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
