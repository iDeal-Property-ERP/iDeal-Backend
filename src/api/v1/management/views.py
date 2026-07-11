from datetime import date, timedelta
from decimal import Decimal
from http import HTTPStatus

from django.db.models import Case, Count, F, IntegerField, Max, Min, Q, Sum, Value, When
from django.utils.translation import gettext_lazy as _
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
    ManagementAgreementOutput,
    ManagementBookingConvertInput,
    ManagementBookingOutput,
    ManagementInquiryOutput,
    ManagementInquiryStatusInput,
    ManagementLeadOutput,
    ManagementLeaseOutput,
    ManagementOnboardingApproveInput,
    ManagementOnboardingDetailOutput,
    ManagementOnboardingOutput,
    ManagementOnboardingRejectInput,
    ManagementOnboardingRequestInfoInput,
    ManagementPaymentOutput,
    ManagementPayoutOutput,
    ManagementPropertyOutput,
    ManagementServiceRequestOutput,
    ManagementUserCreateInput,
    ManagementUserOutput,
    ManagementUserUpdateInput,
    ManagementViewingProposeTimeInput,
    ManagementViewingRequestOutput,
    MonthlyPnlRow,
    PnlBreakdown,
    PnlBreakdownRow,
    PnlServiceTypeRow,
    PnLSummaryCard,
    PnLSummaryOutput,
    RecentPaymentRow,
    ServiceRequestCommentCreateInput,
    ServiceRequestCommentOutput,
)
from api.v1.vas.schemas import ManagementServiceOrderCreateInput, ServiceOrderStatusInput
from core.api.permissions import RoleAuth
from core.api.views import BaseController, DetailPath, GenericController, ListAPIView, ListQuery
from core.constants import BookingStatus, PaymentStatus, PayoutStatus, UserRole, ViewingRequestStatus
from core.utils.pagination import build_paginated_response


def _d(value):
    return str(value.quantize(Decimal("0.01")))


def _month_end(today: date) -> date:
    import calendar

    return today.replace(day=calendar.monthrange(today.year, today.month)[1])


def _sum_usd(qs, field: str = "amount") -> str:
    """Sum ``field`` across a queryset, converting each currency bucket to USD.

    Best-effort like the finance dashboard: an empty exchange-rate table makes a
    UZS→USD conversion fall back to that bucket contributing 0 rather than
    raising, so the KPI degrades gracefully instead of 500-ing.
    """
    from finance.utils import convert_amount

    total = Decimal("0.00")
    for row in qs.values("currency").annotate(bucket=Sum(field)):
        amount = row["bucket"] or Decimal("0.00")
        currency = row["currency"]
        if currency == "USD":
            total += amount
        else:
            try:
                total += convert_amount(amount, currency, "USD")
            except ValueError:
                continue
    return str(total.quantize(Decimal("0.01")))


def _payouts_due_usd() -> str:
    """Total scheduled owner payouts on/before the next run — the 'payouts due' KPI."""
    from finance.models import PayoutSchedule
    from finance.services import next_payout_run_date

    next_run = next_payout_run_date(date.today())
    qs = PayoutSchedule.objects.filter(status=PayoutStatus.SCHEDULED, scheduled_date__lte=next_run)
    return _sum_usd(qs)


def _optional_json(request) -> dict:
    """Best-effort parse of a JSON request body; ``{}`` when absent or invalid.

    Mirrors the finance-views helper: lets detail-action endpoints accept an
    optional body without the dmr framework rejecting a body-less request.
    """
    import json

    raw = getattr(request, "body", b"") or b""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# Lead triage tabs → per-source status sets. A lead is a ViewingRequest or a
# Booking; the queue merges both and buckets them into four workflow tabs.
_LEAD_TAB_VIEWING = {
    "new": [ViewingRequestStatus.PENDING],
    "scheduled": [ViewingRequestStatus.CONFIRMED],
    "awaiting": [],
    "closed": [ViewingRequestStatus.CANCELLED],
}
_LEAD_TAB_BOOKING = {
    "new": [BookingStatus.REQUESTED],
    "scheduled": [],
    "awaiting": [BookingStatus.APPROVED],
    "closed": [BookingStatus.REJECTED, BookingStatus.CANCELLED, BookingStatus.CONVERTED],
}


class ManagementView(BaseController):
    auth = (RoleAuth(UserRole.MANAGEMENT),)


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
            inc = Payment.objects.filter(status="paid", payment_date__year=year, payment_date__month=month).aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0.00")
            out = PayoutSchedule.objects.filter(status="paid", paid_date__year=year, paid_date__month=month).aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0.00")
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
        loss_per_day = sum((p / Decimal("30")) for p in vacant_props if p) if vacant_props else Decimal("0.00")

        # ---- Recent Payments ----
        recent_payments_qs = Payment.objects.select_related("tenant", "lease__property").order_by("-payment_date")[:5]
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
            entry["status"]: entry["count"] for entry in Property.objects.values("status").annotate(count=Count("id"))
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
                payments_received=KpiPaymentsReceived(amount=_d(payments_amount), days=25, on_time_pct=on_time_pct),
                vacant=KpiVacant(value=vacant_count, loss_per_day=_d(loss_per_day)),
            ),
            recent_payments=recent_payments,
            occupancy=DashboardOccupancy(rate=occ_rate, rented=rented, vacant=vacant, maintenance=maintenance),
            maintenance_requests=maintenance_requests,
        )

        return self.ok(output.model_dump(mode="json"))


# P&L revenue streams (lease, vas) and expense streams (payouts, maintenance).
# The ``sources`` query param picks which streams are included; the default
# reproduces the pre-phase-6 math exactly (lease payments vs. owner payouts).
_PNL_REVENUE_SOURCES = ("lease", "vas")
_PNL_EXPENSE_SOURCES = ("payouts", "maintenance")
_PNL_SOURCES = _PNL_REVENUE_SOURCES + _PNL_EXPENSE_SOURCES
_PNL_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _pnl_parse_sources(raw: str | None) -> list[str]:
    if not raw:
        return ["lease", "payouts"]
    picked = [s for s in (part.strip() for part in raw.split(",")) if s in _PNL_SOURCES]
    return picked or ["lease", "payouts"]


def _pnl_month_buckets(year: int, month: int, convert) -> dict[str, Decimal]:
    """UZS totals per source for one month.

    VAS commission is attributed to the completion month (``completed_at``,
    falling back to ``updated_at`` for legacy rows completed before the field
    existed). Maintenance counts platform-borne resolved costs only; a null
    bearer buckets as platform, mirroring the maintenance stats endpoint.
    Maintenance costs carry no currency column and are assumed USD (phase-5 gap).
    """
    from finance.models import Payment, PayoutSchedule
    from maintenance.models import ServiceRequest
    from vas.models import ServiceOrder

    from core.constants import CostBearer, ServiceRequestStatus, VASOrderStatus

    lease = Decimal("0.00")
    for p in Payment.objects.filter(status="paid", payment_date__year=year, payment_date__month=month):
        lease += convert(p.amount, p.currency, "UZS")

    vas = Decimal("0.00")
    vas_orders = ServiceOrder.objects.filter(status=VASOrderStatus.COMPLETED).filter(
        Q(completed_at__year=year, completed_at__month=month)
        | Q(completed_at__isnull=True, updated_at__year=year, updated_at__month=month)
    )
    for o in vas_orders:
        vas += convert(o.commission_earned, o.currency, "UZS")

    payouts = Decimal("0.00")
    for po in PayoutSchedule.objects.filter(status="paid", paid_date__year=year, paid_date__month=month):
        payouts += convert(po.amount, po.currency, "UZS")

    maintenance = Decimal("0.00")
    maint_qs = ServiceRequest.objects.filter(
        status=ServiceRequestStatus.RESOLVED,
        resolved_at__year=year,
        resolved_at__month=month,
        cost__isnull=False,
    ).exclude(cost_bearer=CostBearer.OWNER)
    for sr in maint_qs:
        maintenance += convert(sr.cost, "USD", "UZS")

    return {"lease": lease, "vas": vas, "payouts": payouts, "maintenance": maintenance}


def _pnl_projection(growth_actual, last_month):
    projected = []
    if len(growth_actual) < 2:
        return projected
    last3_revenues = [Decimal(r.revenue) for r in growth_actual[-3:]]
    if last3_revenues[0] <= 0:
        return projected
    avg_growth = sum(
        (last3_revenues[i + 1] - last3_revenues[i]) / last3_revenues[i] for i in range(len(last3_revenues) - 1)
    ) / (len(last3_revenues) - 1)
    last_rev = last3_revenues[-1]
    for i in range(1, 4):
        proj_month = last_month + i
        if proj_month > 12:
            break
        last_rev = last_rev * (Decimal("1") + avg_growth)
        projected.append(GrowthPoint(month=_PNL_MONTH_NAMES[proj_month - 1], revenue=_d(last_rev)))
    return projected


def _pnl_breakdown(totals: dict, sources: list[str], convert, currency: str, year: int):
    """Whole-period revenue/expense composition + VAS commission by service type."""
    from vas.models import ServiceOrder

    from core.constants import VASOrderStatus

    def rows(names):
        picked = [s for s in names if s in sources]
        total = sum((totals[s] for s in picked), Decimal("0.00"))
        out = []
        for s in picked:
            share = (totals[s] / total * Decimal("100")).quantize(Decimal("0.1")) if total > 0 else Decimal("0.0")
            out.append(PnlBreakdownRow(source=s, amount=_d(convert(totals[s], "UZS", currency)), share=str(share)))
        return out

    by_type = []
    if "vas" in sources:
        vas_orders = (
            ServiceOrder.objects.filter(status=VASOrderStatus.COMPLETED)
            .filter(Q(completed_at__year=year) | Q(completed_at__isnull=True, updated_at__year=year))
            .select_related("catalog_item")
        )
        type_totals: dict[str, Decimal] = {}
        for o in vas_orders:
            uzs = convert(o.commission_earned, o.currency, "UZS")
            type_totals[o.catalog_item.service_type] = (
                type_totals.get(o.catalog_item.service_type, Decimal("0.00")) + uzs
            )
        by_type = [
            PnlServiceTypeRow(service_type=k, amount=_d(convert(v, "UZS", currency)))
            for k, v in sorted(type_totals.items())
        ]

    return PnlBreakdown(
        revenue=rows(_PNL_REVENUE_SOURCES), expenses=rows(_PNL_EXPENSE_SOURCES), vas_by_service_type=by_type
    )


class PnLSummaryView(ManagementView):
    """P&L report.

    Query params (all optional; the param-less call is byte-compatible with the
    pre-phase-6 response apart from additive keys):
    - ``year``      report year, default current
    - ``currency``  USD (default) or UZS consolidation; ``tax`` stays UZS as before
    - ``sources``   csv of lease,vas,payouts,maintenance; default lease,payouts
    """

    def get(self) -> dict:
        from finance.utils import convert_amount
        from property.models import Property

        today = date.today()
        params = self.request.GET
        year_raw = params.get("year") or ""
        year = int(year_raw) if year_raw.isdigit() else today.year
        currency = (params.get("currency") or "USD").upper()
        if currency not in ("USD", "UZS"):
            currency = "USD"
        sources = _pnl_parse_sources(params.get("sources"))

        def _convert(amount, from_currency, to_currency):
            if from_currency == to_currency:
                return Decimal(str(amount))
            if float(amount) == 0:
                return Decimal("0.00")
            try:
                return convert_amount(amount, from_currency, to_currency)
            except ValueError:
                return Decimal("0.00")

        last_month = today.month if year == today.year else 12
        totals = {s: Decimal("0.00") for s in _PNL_SOURCES}
        monthly_rows = []
        growth_actual = []
        current_revenue = current_expenses = current_net = current_tax = Decimal("0.00")

        for m in range(1, last_month + 1):
            buckets = _pnl_month_buckets(year, m, _convert)
            for s in _PNL_SOURCES:
                totals[s] += buckets[s]
            revenue_uzs = sum((buckets[s] for s in _PNL_REVENUE_SOURCES if s in sources), Decimal("0.00"))
            expenses_uzs = sum((buckets[s] for s in _PNL_EXPENSE_SOURCES if s in sources), Decimal("0.00"))
            net_uzs = revenue_uzs - expenses_uzs
            tax_uzs = net_uzs * Decimal("0.04")

            revenue_out = _convert(revenue_uzs, "UZS", currency)
            expenses_out = _convert(expenses_uzs, "UZS", currency)
            net_out = _convert(net_uzs, "UZS", currency)

            monthly_rows.append(
                MonthlyPnlRow(
                    month=_PNL_MONTH_NAMES[m - 1],
                    revenue=_d(revenue_out),
                    owner_payouts=_d(expenses_out),
                    profit=_d(net_out),
                    tax=_d(tax_uzs),
                )
            )
            growth_actual.append(GrowthPoint(month=_PNL_MONTH_NAMES[m - 1], revenue=_d(revenue_out)))

            if m == last_month:
                current_revenue, current_expenses = revenue_out, expenses_out
                current_net, current_tax = net_out, tax_uzs

        summary = PnLSummaryCard(
            gross_revenue=_d(current_revenue),
            owner_payouts=_d(current_expenses),
            net_profit=_d(current_net),
            tax=_d(current_tax),
        )

        growth_projected = _pnl_projection(growth_actual, last_month) if year == today.year else []

        total_properties = Property.objects.count()
        per_property_net = current_net / total_properties if total_properties > 0 else Decimal("0.00")
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
            year=year,
            currency=currency,
            sources=sources,
            breakdown=_pnl_breakdown(totals, sources, _convert, currency, year),
        )

        return self.ok(output.model_dump(mode="json"))


class ManagementUserListView(ManagementView, ListAPIView):
    output_schema = ManagementUserOutput

    def get_queryset(self):
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
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementUserInviteView(ManagementView, GenericController):
    output_schema = ManagementUserOutput

    def post(self, parsed_body: Body[ManagementUserCreateInput]) -> dict:
        import secrets

        from account.models import User

        if parsed_body.role not in UserRole.values():
            return self.fail(error=str(_("Invalid role")))

        base_username = parsed_body.email.split("@")[0]
        username = base_username
        suffix = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{suffix}"
            suffix += 1

        # Give the invited user a usable temporary password so they can actually
        # log in, and flag them to set their own on first login. The temp password
        # is returned once for the manager to relay; it is never stored in clear.
        temp_password = secrets.token_urlsafe(9)
        user = User.objects.create_user(
            username=username,
            password=temp_password,
            first_name=parsed_body.first_name,
            last_name=parsed_body.last_name,
            email=parsed_body.email,
            phone=parsed_body.phone,
            role=parsed_body.role,
            is_active=parsed_body.is_active,
            is_verified=parsed_body.is_verified,
            is_staff=(parsed_body.role == UserRole.MANAGEMENT),
            must_change_password=True,
        )
        data = self.to_output(user)
        data["temporary_password"] = temp_password
        return self.ok(data, status_code=HTTPStatus.CREATED)


class ManagementUserDetailUpdateView(ManagementView, GenericController):
    output_schema = ManagementUserOutput

    def get_queryset(self):
        from account.models import User

        return User.objects.all()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        return self.ok(self.to_output(instance))

    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementUserUpdateInput]) -> dict:
        from account.models import User

        instance = self.get_object(pk=parsed_path.pk)
        data = parsed_body.model_dump(exclude_unset=True)
        if data.get("role") and data["role"] not in UserRole.values():
            return self.fail(error=str(_("Invalid role")))
        for field in ("email", "phone"):
            value = data.get(field)
            if value and User.objects.filter(**{field: value}).exclude(pk=instance.pk).exists():
                return self.fail(
                    error=str(_("This %s is already in use") % field),
                    message=str(_("Data conflict")),
                    status_code=HTTPStatus.CONFLICT,
                )
        instance = self.perform_update(instance, data)
        return self.ok(self.to_output(instance))


class ManagementAssigneeListView(ManagementView):
    """Staff users eligible for maintenance assignment — the ``assigned_to``
    options list. Mirrors the user workbench's role=mgmt filter."""

    def get(self) -> dict:
        from account.models import User

        staff = User.objects.filter(role=UserRole.MANAGEMENT, is_active=True).order_by("first_name", "last_name", "id")
        return self.ok([{"id": u.id, "full_name": f"{u.first_name} {u.last_name or ''}".strip()} for u in staff])


class ManagementPropertyListView(ManagementView, ListAPIView):
    output_schema = ManagementPropertyOutput

    def get_queryset(self):
        from contract.models import Lease
        from django.db.models import Prefetch
        from property.models import Property

        from core.constants import LeaseStatus, PropertyStatus

        qs = (
            Property.objects.select_related("district", "owner")
            .prefetch_related(
                Prefetch(
                    "leases",
                    queryset=Lease.objects.filter(status=LeaseStatus.ACTIVE).select_related("tenant"),
                    to_attr="active_leases",
                )
            )
            .order_by("-created_at")
        )
        status = self.request.GET.get("status")
        district_id = self.request.GET.get("district_id")
        tariff = self.request.GET.get("tariff")
        search = self.request.GET.get("search")

        # Drafts live behind their own saved-view tab, not the default portfolio.
        qs = qs.filter(status=status) if status else qs.exclude(status=PropertyStatus.DRAFT)
        if district_id:
            qs = qs.filter(district_id=district_id)
        if tariff:
            qs = qs.filter(tariff=tariff)
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(address__icontains=search))
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementPropertyMapView(ManagementView):
    """Geocoded portfolio for the map screen — all statuses, non-paginated.

    Sized for portfolio scale (hundreds of rows); ``bbox`` (minLon,minLat,maxLon,maxLat)
    is the escape hatch if the portfolio outgrows a single response. Rows are a
    superset of ManagementPropertyOutput so the frontend can hand a marker's row
    straight to the property record panel.
    """

    def get(self) -> dict:
        from contract.models import Lease
        from django.db.models import Prefetch
        from property.models import Property

        from core.constants import LeaseStatus, PropertyStatus

        params = self.request.GET
        qs = (
            Property.objects.select_related("district", "owner")
            .exclude(status=PropertyStatus.DRAFT)
            .exclude(Q(map_lat__isnull=True) | Q(map_lon__isnull=True))
            .prefetch_related(
                Prefetch(
                    "leases",
                    queryset=Lease.objects.filter(status=LeaseStatus.ACTIVE).select_related("tenant"),
                    to_attr="active_leases",
                )
            )
            .order_by("-created_at")
        )
        for field, param in (
            ("status", "status"),
            ("district_id", "district_id"),
            ("tariff", "tariff"),
            ("rooms", "rooms"),
            ("tenant_charge_price__gte", "price_min"),
            ("tenant_charge_price__lte", "price_max"),
        ):
            value = params.get(param)
            if value:
                qs = qs.filter(**{field: value})
        search = params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(address__icontains=search))
        bbox = params.get("bbox")
        if bbox:
            parts = bbox.split(",")
            if len(parts) == 4:
                try:
                    min_lon, min_lat, max_lon, max_lat = (Decimal(p) for p in parts)
                except ArithmeticError:
                    pass
                else:
                    qs = qs.filter(
                        map_lon__gte=min_lon, map_lon__lte=max_lon, map_lat__gte=min_lat, map_lat__lte=max_lat
                    )

        rows = []
        for prop in qs:
            row = ManagementPropertyOutput.model_validate(prop).model_dump(mode="json")
            lease = prop.active_leases[0] if prop.active_leases else None
            row["tenant_name"] = f"{lease.tenant.first_name} {lease.tenant.last_name or ''}".strip() if lease else None
            row["lease_end_date"] = lease.end_date.isoformat() if lease else None
            rows.append(row)
        return self.ok(rows)


class ManagementPropertyImportView(ManagementView):
    """Bulk-create properties from a CSV upload.

    Accepts multipart form data with the CSV under ``file`` (fallback: a JSON
    body ``{"csv_text": "..."}``). Columns mirror ``PropertyCreateInput`` — the
    same schema the single-create endpoint validates with — so required columns
    are: name, address, district_id, rooms, area_sqm, floor, owner_id,
    ask_price, owner_guaranteed_price, tenant_charge_price. Optional columns
    (total_floors, status, tariff, description, map_lat, map_lon, currencies…)
    are honored when present. Import is per-row: valid rows are created, invalid
    rows are reported back with their 1-based CSV line number (header = row 1).
    """

    def post(self) -> dict:
        import csv
        import io

        from django.db import transaction
        from property.models import Property
        from pydantic import ValidationError

        from api.v1.property.schemas import PropertyCreateInput

        # Multipart parsing consumes the request stream, so only touch
        # request.body (the csv_text fallback) on non-multipart requests.
        content_type = self.request.content_type or ""
        if content_type.startswith("multipart"):
            upload = self.request.FILES.get("file")
            if upload is None:
                csv_text = ""
            else:
                try:
                    csv_text = upload.read().decode("utf-8-sig")
                except UnicodeDecodeError:
                    return self.fail(
                        error=str(_("The file is not valid UTF-8 text")), message=str(_("Validation error"))
                    )
        else:
            csv_text = _optional_json(self.request).get("csv_text") or ""
        if not csv_text.strip():
            return self.fail(
                error=str(_("Provide a CSV file under 'file' or a 'csv_text' body field")),
                message=str(_("Validation error")),
            )

        reader = csv.DictReader(io.StringIO(csv_text))
        if not reader.fieldnames:
            return self.fail(error=str(_("The CSV has no header row")), message=str(_("Validation error")))

        allowed = set(PropertyCreateInput.model_fields)
        created = 0
        errors = []
        for line_no, raw_row in enumerate(reader, start=2):
            # Empty cells fall back to the schema's defaults; unknown columns are ignored.
            row = {k.strip(): v.strip() for k, v in raw_row.items() if k and k.strip() in allowed and v and v.strip()}
            try:
                validated = PropertyCreateInput.model_validate(row)
            except ValidationError as err:
                messages = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in err.errors())
                errors.append({"row": line_no, "message": messages})
                continue
            try:
                with transaction.atomic():
                    Property.objects.create(**validated.model_dump())
            except Exception as err:  # noqa: BLE001 — per-row report, never a 500
                errors.append({"row": line_no, "message": str(err)})
                continue
            created += 1

        return self.ok({"created": created, "errors": errors}, status_code=HTTPStatus.CREATED if created else None)


class LeaseListView(ManagementView, ListAPIView):
    output_schema = ManagementLeaseOutput

    def get_queryset(self):
        from contract.models import Lease

        qs = Lease.objects.select_related("property", "tenant").order_by("-created_at")
        status = self.request.GET.get("status")
        property_id = self.request.GET.get("property_id")
        tenant_id = self.request.GET.get("tenant_id")
        search = self.request.GET.get("search")
        ends_within = self.request.GET.get("ends_within")

        if status:
            qs = qs.filter(status=status)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if search:
            cond = (
                Q(tenant__first_name__icontains=search)
                | Q(tenant__last_name__icontains=search)
                | Q(property__name__icontains=search)
            )
            if search.isdigit():
                cond |= Q(id=int(search))
            qs = qs.filter(cond)
        if ends_within and ends_within.isdigit():
            today = date.today()
            qs = qs.filter(end_date__gte=today, end_date__lte=today + timedelta(days=int(ends_within)))
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class OwnerAgreementListView(ManagementView, ListAPIView):
    output_schema = ManagementAgreementOutput

    def get_queryset(self):
        from contract.models import OwnerAgreement

        qs = OwnerAgreement.objects.select_related("owner", "property").order_by("-created_at")
        status = self.request.GET.get("status")
        owner_id = self.request.GET.get("owner_id")
        property_id = self.request.GET.get("property_id")
        search = self.request.GET.get("search")
        ends_within = self.request.GET.get("ends_within")

        if status:
            qs = qs.filter(status=status)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if search:
            qs = qs.filter(
                Q(owner__first_name__icontains=search)
                | Q(owner__last_name__icontains=search)
                | Q(agreement_number__icontains=search)
            )
        if ends_within and ends_within.isdigit():
            today = date.today()
            qs = qs.filter(end_date__gte=today, end_date__lte=today + timedelta(days=int(ends_within)))
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


# "Most overdue" first = earliest due date; the frontend sort values map here.
_PAYMENT_ORDERINGS = {
    "due_date": ["due_date", "-id"],
    "-due_date": ["-due_date", "-id"],
    "payment_date": ["payment_date", "-id"],
    "-payment_date": ["-payment_date", "-id"],
    "amount": ["amount", "-id"],
    "-amount": ["-amount", "-id"],
}
_PAYOUT_ORDERINGS = {
    "scheduled_date": ["scheduled_date", "-id"],
    "-scheduled_date": ["-scheduled_date", "-id"],
    "amount": ["amount", "-id"],
    "-amount": ["-amount", "-id"],
    "-created_at": ["-created_at"],
}


class PaymentListView(ManagementView, ListAPIView):
    output_schema = ManagementPaymentOutput

    def get_queryset(self):
        from finance.models import Payment
        from finance.utils import overdue_q

        qs = Payment.objects.select_related("tenant", "lease__property").order_by("-payment_date")
        status = self.request.GET.get("status")
        method = self.request.GET.get("method")
        lease_id = self.request.GET.get("lease_id")
        tenant_id = self.request.GET.get("tenant_id")
        property_id = self.request.GET.get("property_id")
        search = self.request.GET.get("search")
        overdue = self.request.GET.get("overdue")
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")
        due_from = self.request.GET.get("due_from")
        due_to = self.request.GET.get("due_to")
        order = self.request.GET.get("order")

        if status:
            qs = qs.filter(status=status)
        if method:
            qs = qs.filter(method=method)
        if lease_id:
            qs = qs.filter(lease_id=lease_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if property_id:
            qs = qs.filter(lease__property_id=property_id)
        if search:
            cond = (
                Q(tenant__first_name__icontains=search)
                | Q(tenant__last_name__icontains=search)
                | Q(lease__property__name__icontains=search)
            )
            if search.isdigit():
                cond |= Q(id=int(search)) | Q(lease_id=int(search))
            qs = qs.filter(cond)
        if overdue in ("true", "1"):
            qs = qs.filter(overdue_q(date.today()))
        if date_from:
            qs = qs.filter(payment_date__gte=date_from)
        if date_to:
            qs = qs.filter(payment_date__lte=date_to)
        if due_from:
            qs = qs.filter(due_date__gte=due_from)
        if due_to:
            qs = qs.filter(due_date__lte=due_to)
        if order in _PAYMENT_ORDERINGS:
            qs = qs.order_by(*_PAYMENT_ORDERINGS[order])
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class PayoutListView(ManagementView, ListAPIView):
    output_schema = ManagementPayoutOutput

    def get_queryset(self):
        from finance.models import PayoutSchedule

        qs = PayoutSchedule.objects.select_related("owner", "owner_agreement__property", "source_payment").order_by(
            "-scheduled_date"
        )
        status = self.request.GET.get("status")
        owner_id = self.request.GET.get("owner_id")
        search = self.request.GET.get("search")
        scheduled_from = self.request.GET.get("scheduled_from")
        scheduled_to = self.request.GET.get("scheduled_to")
        order = self.request.GET.get("order")

        if status:
            qs = qs.filter(status=status)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        if search:
            cond = (
                Q(owner__first_name__icontains=search)
                | Q(owner__last_name__icontains=search)
                | Q(owner_agreement__property__name__icontains=search)
            )
            if search.isdigit():
                cond |= Q(id=int(search))
            qs = qs.filter(cond)
        if scheduled_from:
            qs = qs.filter(scheduled_date__gte=scheduled_from)
        if scheduled_to:
            qs = qs.filter(scheduled_date__lte=scheduled_to)
        if order in _PAYOUT_ORDERINGS:
            qs = qs.order_by(*_PAYOUT_ORDERINGS[order])
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class PaymentStatsView(ManagementView):
    """Aggregate money totals for the Payments workbench KPI strip.

    All sums are converted to USD (mixed-currency safe) using the same
    best-effort conversion the finance dashboard uses; an empty exchange-rate
    table degrades to raw same-currency sums rather than erroring.
    """

    def get(self) -> dict:
        from finance.models import Payment
        from finance.utils import overdue_q

        today = date.today()
        month_start = today.replace(day=1)
        search = self.request.GET.get("search")

        base = Payment.objects.all()
        if search:
            cond = (
                Q(tenant__first_name__icontains=search)
                | Q(tenant__last_name__icontains=search)
                | Q(lease__property__name__icontains=search)
            )
            if search.isdigit():
                cond |= Q(id=int(search)) | Q(lease_id=int(search))
            base = base.filter(cond)

        overdue = overdue_q(today)
        collected_month = base.filter(status=PaymentStatus.PAID, payment_date__gte=month_start, payment_date__lte=today)
        outstanding = base.filter(Q(status=PaymentStatus.PENDING) | Q(status=PaymentStatus.OVERDUE))
        overdue_qs = base.filter(overdue)
        due_month = base.filter(
            status=PaymentStatus.PENDING, due_date__gte=month_start, due_date__lte=_month_end(today)
        )

        return self.ok(
            {
                "month": today.strftime("%Y-%m"),
                "collected_month": _sum_usd(collected_month),
                "outstanding": _sum_usd(outstanding),
                "overdue_total": _sum_usd(overdue_qs),
                "payouts_due": _payouts_due_usd(),
                "counts": {
                    "overdue": overdue_qs.count(),
                    "due_month": due_month.count(),
                    "paid_month": collected_month.count(),
                    "all": base.count(),
                },
            }
        )


class PayoutStatsView(ManagementView):
    """Aggregate money totals for the Payouts workbench KPI strip."""

    def get(self) -> dict:
        from finance.models import PayoutSchedule
        from finance.services import next_payout_run_date

        today = date.today()
        month_start = today.replace(day=1)
        next_run = next_payout_run_date(today)

        base = PayoutSchedule.objects.all()
        due = base.filter(status=PayoutStatus.SCHEDULED)
        held = base.filter(status=PayoutStatus.HELD)
        paid = base.filter(status=PayoutStatus.PAID)
        cancelled = base.filter(status=PayoutStatus.CANCELLED)

        return self.ok(
            {
                "next_run_date": next_run.isoformat(),
                "due_next_run": _sum_usd(due.filter(scheduled_date__lte=next_run)),
                "this_month": _sum_usd(
                    base.filter(scheduled_date__gte=month_start, scheduled_date__lte=_month_end(today))
                ),
                "held_total": _sum_usd(held),
                "next_30_days": _sum_usd(
                    due.filter(scheduled_date__gte=today, scheduled_date__lte=today + timedelta(days=30))
                ),
                "counts": {
                    "due": due.count(),
                    "held": held.count(),
                    "paid": paid.count(),
                    "cancelled": cancelled.count(),
                    "all": base.count(),
                },
            }
        )


_SERVICE_REQUEST_ORDERINGS = {
    "recent": ("-created_at",),
    "oldest": ("created_at",),
    "cost": ("-cost", "-created_at"),
}


def _service_priority_rank():
    """Order-by expression ranking Critical → High → Medium → Low (0..3)."""
    from core.constants import ServiceRequestPriority as P

    return Case(
        When(priority=P.CRITICAL, then=Value(0)),
        When(priority=P.HIGH, then=Value(1)),
        When(priority=P.MEDIUM, then=Value(2)),
        When(priority=P.LOW, then=Value(3)),
        default=Value(4),
        output_field=IntegerField(),
    )


class ManagementServiceRequestListView(ManagementView, ListAPIView):
    output_schema = ManagementServiceRequestOutput

    def get_queryset(self):
        from maintenance.models import ServiceRequest

        qs = (
            ServiceRequest.objects.select_related("property", "tenant", "assigned_to")
            .prefetch_related("photos")
            .order_by("-created_at")
        )
        status = self.request.GET.get("status")
        priority = self.request.GET.get("priority")
        property_id = self.request.GET.get("property_id")
        tenant_id = self.request.GET.get("tenant_id")
        assigned_to_id = self.request.GET.get("assigned_to_id")
        unassigned = self.request.GET.get("unassigned")
        search = self.request.GET.get("search")
        order = self.request.GET.get("order")

        if status:
            qs = qs.filter(status=status)
        if priority:
            qs = qs.filter(priority=priority)
        if property_id:
            qs = qs.filter(property_id=property_id)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if assigned_to_id:
            qs = qs.filter(assigned_to_id=assigned_to_id)
        if unassigned in ("true", "1"):
            qs = qs.filter(assigned_to__isnull=True)
        if search:
            cond = (
                Q(title__icontains=search)
                | Q(property__name__icontains=search)
                | Q(tenant__first_name__icontains=search)
                | Q(tenant__last_name__icontains=search)
            )
            if search.isdigit():
                cond |= Q(id=int(search))
            qs = qs.filter(cond)
        if order == "priority":
            qs = qs.annotate(_prank=_service_priority_rank()).order_by("_prank", "-created_at")
        elif order in _SERVICE_REQUEST_ORDERINGS:
            qs = qs.order_by(*_SERVICE_REQUEST_ORDERINGS[order])
        return qs

    def to_output(self, instance):
        data = super().to_output(instance)
        data["photo_urls"] = [self.request.build_absolute_uri(p.image.url) for p in instance.photos.all()]
        return data

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementServiceRequestStatsView(ManagementView):
    """KPI strip for the Maintenance workbench: open/in-progress/resolved + cost."""

    def get(self) -> dict:
        from django.db.models import Avg, DurationField, ExpressionWrapper
        from django.db.models.functions import Coalesce, Now
        from maintenance.models import ServiceRequest

        from core.constants import CostBearer, ServiceRequestStatus

        today = date.today()
        window_start = today - timedelta(days=30)
        base = ServiceRequest.objects.all()

        open_qs = base.filter(status=ServiceRequestStatus.OPEN)
        in_progress_qs = base.filter(status=ServiceRequestStatus.IN_PROGRESS)
        resolved_30d = base.filter(
            status=ServiceRequestStatus.RESOLVED,
            resolved_at__date__gte=window_start,
        )

        age_expr = ExpressionWrapper(Now() - F("created_at"), output_field=DurationField())
        in_progress_age = in_progress_qs.aggregate(v=Avg(age_expr))["v"]
        resolution_expr = ExpressionWrapper(
            Coalesce(F("resolved_at"), Now()) - F("created_at"), output_field=DurationField()
        )
        resolved_age = resolved_30d.aggregate(v=Avg(resolution_expr))["v"]

        def _days(delta):
            return round(delta.total_seconds() / 86400, 1) if delta else 0.0

        cost_rows = base.filter(
            status=ServiceRequestStatus.RESOLVED, resolved_at__date__gte=window_start, cost__isnull=False
        )
        total = cost_rows.aggregate(s=Sum("cost"))["s"] or Decimal("0.00")
        owner = cost_rows.filter(cost_bearer=CostBearer.OWNER).aggregate(s=Sum("cost"))["s"] or Decimal("0.00")
        # A null bearer buckets as platform-borne cost.
        platform = total - owner

        return self.ok(
            {
                "open": open_qs.count(),
                "open_unassigned": open_qs.filter(assigned_to__isnull=True).count(),
                "in_progress": in_progress_qs.count(),
                "in_progress_avg_age_days": _days(in_progress_age),
                "resolved_30d": resolved_30d.count(),
                "resolved_30d_avg_days": _days(resolved_age),
                "cost_30d_total": _d(total),
                "cost_30d_owner": _d(owner),
                "cost_30d_platform": _d(platform),
                "counts": {
                    "open": open_qs.count(),
                    "in_progress": in_progress_qs.count(),
                    "resolved": base.filter(status=ServiceRequestStatus.RESOLVED).count(),
                    "all": base.count(),
                },
            }
        )


class _ServiceRequestActionView(ManagementView, GenericController):
    output_schema = ManagementServiceRequestOutput

    def get_queryset(self):
        from maintenance.models import ServiceRequest

        return ServiceRequest.objects.select_related("property", "tenant", "assigned_to").prefetch_related("photos")

    def to_output(self, instance):
        data = super().to_output(instance)
        data["photo_urls"] = [self.request.build_absolute_uri(p.image.url) for p in instance.photos.all()]
        return data


class ManagementServiceRequestCancelView(_ServiceRequestActionView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        from core.constants import ServiceRequestStatus

        sr = self.get_object(pk=parsed_path.pk)
        if sr.status == ServiceRequestStatus.RESOLVED:
            return self.fail(
                error=str(_("A resolved request cannot be cancelled")),
                message=str(_("Invalid status transition")),
            )
        reason = (_optional_json(self.request).get("reason") or "").strip()
        sr.status = ServiceRequestStatus.CANCELLED
        update_fields = ["status", "updated_at"]
        if reason:
            sr.resolution_notes = f"{sr.resolution_notes}\n{reason}" if sr.resolution_notes else reason
            update_fields.append("resolution_notes")
        sr.save(update_fields=update_fields)
        return self.ok(self.to_output(sr), status_code=HTTPStatus.OK)


class ManagementServiceRequestCommentsView(ManagementView, GenericController):
    def get_queryset(self):
        from maintenance.models import ServiceRequest

        return ServiceRequest.objects.all()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        sr = self.get_object(pk=parsed_path.pk)
        comments = sr.comments.select_related("author").order_by("created_at")
        return self.ok([ServiceRequestCommentOutput.model_validate(c).model_dump(mode="json") for c in comments])

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ServiceRequestCommentCreateInput]) -> dict:
        from maintenance.models import ServiceRequestComment

        sr = self.get_object(pk=parsed_path.pk)
        comment = ServiceRequestComment.objects.create(
            service_request=sr, author=self.request.user, body=parsed_body.body
        )
        return self.ok(
            ServiceRequestCommentOutput.model_validate(comment).model_dump(mode="json"),
            status_code=HTTPStatus.CREATED,
        )


class ManagementServiceRequestPhotosView(_ServiceRequestActionView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        from maintenance.models import ServiceRequestPhoto

        from core.utils.uploads import UploadError, save_uploaded_images

        sr = self.get_object(pk=parsed_path.pk)
        files = self.request.FILES.getlist("images")
        if not files:
            return self.fail(error=str(_("No images provided")), message=str(_("Validation error")))
        try:
            save_uploaded_images(ServiceRequestPhoto, "service_request", sr, files)
        except UploadError as err:
            return self.fail(error=str(err), message=str(_("Upload failed")))
        sr.refresh_from_db()
        return self.ok(self.to_output(sr), status_code=HTTPStatus.CREATED)


class ManagementOnboardingListView(ManagementView, ListAPIView):
    output_schema = ManagementOnboardingOutput

    def get_queryset(self):
        from contract.models import OwnerOnboarding

        qs = OwnerOnboarding.objects.select_related("owner", "property").order_by("-created_at")
        status = self.request.GET.get("status")
        search = self.request.GET.get("search")
        if status:
            qs = qs.filter(status=status)
        if search:
            cond = (
                Q(owner__first_name__icontains=search)
                | Q(owner__last_name__icontains=search)
                | Q(property__name__icontains=search)
            )
            if search.isdigit():
                cond |= Q(id=int(search))
            qs = qs.filter(cond)
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementOnboardingDetailView(ManagementView, GenericController):
    output_schema = ManagementOnboardingDetailOutput

    def get_queryset(self):
        from contract.models import OwnerOnboarding

        return OwnerOnboarding.objects.select_related("owner", "property__district").prefetch_related(
            "property__photos"
        )

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        from property.models import Property

        from core.constants import PropertyStatus

        onboarding = self.get_object(pk=parsed_path.pk)
        prop = onboarding.property
        owner = onboarding.owner

        owner_props = Property.objects.filter(owner_id=owner.id).count()

        # District market comps: tenant-charge of active (non-pending) properties
        # in the same district — the basis for the pricing grid.
        comps = (
            Property.objects.filter(district_id=prop.district_id)
            .exclude(status=PropertyStatus.PENDING_REVIEW)
            .exclude(id=prop.id)
        )
        agg = comps.aggregate(lo=Min("tenant_charge_price"), hi=Max("tenant_charge_price"))
        prices = sorted(comps.values_list("tenant_charge_price", flat=True))
        median = prices[len(prices) // 2] if prices else None
        # "Suggested price" targets an iDeal margin ≥ 15% over the owner-guaranteed
        # floor, benchmarked to the district median.
        suggested = (median * Decimal("0.85")).quantize(Decimal("0.01")) if median is not None else None

        photos = [
            self.request.build_absolute_uri(p.image.url)
            for p in prop.photos.all().order_by("-is_primary", "sort_order", "id")
        ]

        data = {
            "id": onboarding.id,
            "number": f"ONB-{onboarding.created_at.year}-{onboarding.id:03d}",
            "owner_id": owner.id,
            "owner_name": f"{owner.first_name} {owner.last_name or ''}".strip(),
            "owner_phone": getattr(owner, "phone", None),
            "owner_properties_count": owner_props,
            "property_id": prop.id,
            "property_name": prop.name,
            "property_address": prop.address,
            "district_name": prop.district.name,
            "rooms": prop.rooms,
            "area_sqm": prop.area_sqm,
            "floor": prop.floor,
            "total_floors": prop.total_floors,
            "tariff": prop.tariff,
            "status": onboarding.status,
            "offer_version": onboarding.offer_version,
            "offer_terms_snapshot": onboarding.offer_terms_snapshot,
            "offer_accepted_at": onboarding.offer_accepted_at,
            "review_notes": onboarding.review_notes,
            "generated_agreement_id": onboarding.generated_agreement_id,
            "ask_price": prop.ask_price,
            "ask_currency": prop.ask_currency,
            "market_min": agg["lo"],
            "market_max": agg["hi"],
            "market_median": median,
            "suggested_price": suggested,
            "photos": photos,
            "created_at": onboarding.created_at,
            "updated_at": onboarding.updated_at,
        }
        return self.ok(self.to_output(data), status_code=HTTPStatus.OK)


class ManagementOnboardingStatsView(ManagementView):
    """Tab counts + open total for the Onboardings queue."""

    def get(self) -> dict:
        from contract.models import OwnerOnboarding

        from core.constants import OnboardingStatus

        base = OwnerOnboarding.objects.all()
        counts = {
            "submitted": base.filter(status=OnboardingStatus.SUBMITTED).count(),
            "offer_accepted": base.filter(status=OnboardingStatus.OFFER_ACCEPTED).count(),
            "approved": base.filter(status=OnboardingStatus.APPROVED).count(),
            "rejected": base.filter(status=OnboardingStatus.REJECTED).count(),
            "all": base.count(),
        }
        return self.ok({"counts": counts, "open": counts["submitted"] + counts["offer_accepted"]})


class ManagementOnboardingRequestInfoView(ManagementView, GenericController):
    output_schema = ManagementOnboardingOutput

    def get_queryset(self):
        from contract.models import OwnerOnboarding

        return OwnerOnboarding.objects.select_related("owner", "property").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementOnboardingRequestInfoInput]) -> dict:
        from django.utils import timezone
        from notification.services import notify

        from core.constants import NotificationType

        onboarding = self.get_object(pk=parsed_path.pk)
        stamp = timezone.now().strftime("%Y-%m-%d %H:%M")
        line = f"[{stamp}] More info requested: {parsed_body.note}"
        onboarding.review_notes = f"{onboarding.review_notes}\n{line}" if onboarding.review_notes else line
        onboarding.save(update_fields=["review_notes", "updated_at"])
        notify(
            recipient=onboarding.owner,
            type=NotificationType.OWNER_ONBOARDING,
            title=str(_("More information requested")),
            body=parsed_body.note,
            related_object_type="owner_onboarding",
            related_object_id=onboarding.id,
        )
        return self.ok(self.to_output(onboarding), status_code=HTTPStatus.OK)


class ManagementOnboardingApproveView(ManagementView, GenericController):
    output_schema = ManagementOnboardingOutput

    def get_queryset(self):
        from contract.models import OwnerOnboarding

        return OwnerOnboarding.objects.select_related("owner", "property").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementOnboardingApproveInput]) -> dict:
        from core.constants import OnboardingStatus

        onboarding = self.get_object(pk=parsed_path.pk)
        if onboarding.status == OnboardingStatus.APPROVED:
            return self.fail(
                error=str(_("This onboarding has already been approved")),
                message=str(_("Invalid status transition")),
            )

        prop = onboarding.property
        if parsed_body.owner_guaranteed_price is not None:
            prop.owner_guaranteed_price = parsed_body.owner_guaranteed_price
        if parsed_body.tenant_charge_price is not None:
            prop.tenant_charge_price = parsed_body.tenant_charge_price
        if parsed_body.owner_guaranteed_price is not None or parsed_body.tenant_charge_price is not None:
            prop.save(update_fields=["owner_guaranteed_price", "tenant_charge_price", "updated_at"])

        onboarding.approve(
            reviewed_by=self.request.user,
            commission_rate=parsed_body.commission_rate,
            start_date=parsed_body.start_date,
            end_date=parsed_body.end_date,
            agreement_number=parsed_body.agreement_number,
            terms=parsed_body.terms,
        )
        return self.ok(self.to_output(onboarding), status_code=HTTPStatus.OK)


class ManagementOnboardingRejectView(ManagementView, GenericController):
    output_schema = ManagementOnboardingOutput

    def get_queryset(self):
        from contract.models import OwnerOnboarding

        return OwnerOnboarding.objects.select_related("owner", "property").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementOnboardingRejectInput]) -> dict:
        from core.constants import OnboardingStatus

        onboarding = self.get_object(pk=parsed_path.pk)
        if onboarding.status == OnboardingStatus.APPROVED:
            return self.fail(
                error=str(_("Cannot reject an onboarding that has already been approved")),
                message=str(_("Invalid status transition")),
            )
        onboarding.reject(reviewed_by=self.request.user, review_notes=parsed_body.review_notes)
        return self.ok(self.to_output(onboarding), status_code=HTTPStatus.OK)


class ManagementBookingListView(ManagementView, ListAPIView):
    output_schema = ManagementBookingOutput

    def get_queryset(self):
        from marketplace.models import Booking

        qs = Booking.objects.select_related("property", "tenant", "listing").order_by("-created_at")
        status = self.request.GET.get("status")
        listing_id = self.request.GET.get("listing_id")
        if status:
            qs = qs.filter(status=status)
        if listing_id:
            qs = qs.filter(listing_id=listing_id)
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementBookingView(ManagementView, GenericController):
    output_schema = ManagementBookingOutput

    def get_queryset(self):
        from marketplace.models import Booking

        return Booking.objects.select_related("property", "tenant", "listing").all()


class ManagementBookingApproveView(ManagementBookingView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        from notification.services import notify

        from core.constants import BookingStatus, NotificationType

        booking = self.get_object(pk=parsed_path.pk)
        if booking.status != BookingStatus.REQUESTED:
            return self.fail(
                error=str(_("Only requested bookings can be approved")),
                message=str(_("Invalid status transition")),
            )
        booking.status = BookingStatus.APPROVED
        booking.reviewed_by = self.request.user
        booking.save(update_fields=["status", "reviewed_by", "updated_at"])
        notify(
            recipient=booking.tenant,
            type=NotificationType.BOOKING_STATUS,
            title=str(_("Booking approved")),
            body=str(_("Your booking for %(name)s was approved.")) % {"name": booking.property.name},
            related_object_type="booking",
            related_object_id=booking.id,
        )
        return self.ok(self.to_output(booking), status_code=HTTPStatus.OK)


class ManagementBookingRejectView(ManagementBookingView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        from notification.services import notify

        from core.constants import BookingStatus, NotificationType

        booking = self.get_object(pk=parsed_path.pk)
        if booking.status in (BookingStatus.CONVERTED, BookingStatus.CANCELLED):
            return self.fail(
                error=str(_("This booking can no longer be rejected")),
                message=str(_("Invalid status transition")),
            )
        booking.status = BookingStatus.REJECTED
        booking.reviewed_by = self.request.user
        booking.save(update_fields=["status", "reviewed_by", "updated_at"])
        notify(
            recipient=booking.tenant,
            type=NotificationType.BOOKING_STATUS,
            title=str(_("Booking rejected")),
            body=str(_("Your booking for %(name)s was not approved.")) % {"name": booking.property.name},
            related_object_type="booking",
            related_object_id=booking.id,
        )
        return self.ok(self.to_output(booking), status_code=HTTPStatus.OK)


class ManagementBookingConvertView(ManagementBookingView):
    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementBookingConvertInput]) -> dict:
        from marketplace.models import LeaseConflictError

        booking = self.get_object(pk=parsed_path.pk)
        try:
            booking.convert_to_lease(
                reviewed_by=self.request.user,
                owner_agreement_id=parsed_body.owner_agreement_id,
                monthly_rent=parsed_body.monthly_rent,
                deposit=parsed_body.deposit,
                start_date=parsed_body.start_date,
                end_date=parsed_body.end_date,
            )
        except LeaseConflictError:
            return self.fail(
                error="lease_conflict",
                message=str(_("This property already has an active lease")),
                status_code=HTTPStatus.CONFLICT,
            )
        except ValueError as err:
            return self.fail(error=str(err), message=str(_("Cannot convert booking")))
        return self.ok(self.to_output(booking), status_code=HTTPStatus.OK)


class ManagementViewingRequestListView(ManagementView, ListAPIView):
    output_schema = ManagementViewingRequestOutput

    def get_queryset(self):
        from marketplace.models import ViewingRequest

        qs = ViewingRequest.objects.select_related("listing__property").order_by("-created_at")
        status = self.request.GET.get("status")
        listing_id = self.request.GET.get("listing_id")
        if status:
            qs = qs.filter(status=status)
        if listing_id:
            qs = qs.filter(listing_id=listing_id)
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementInquiryListView(ManagementView, ListAPIView):
    output_schema = ManagementInquiryOutput

    def get_queryset(self):
        from marketplace.models import ContactInquiry

        qs = ContactInquiry.objects.order_by("-created_at")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementInquiryStatusView(ManagementView, GenericController):
    output_schema = ManagementInquiryOutput

    def get_queryset(self):
        from marketplace.models import ContactInquiry

        return ContactInquiry.objects.all()

    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementInquiryStatusInput]) -> dict:
        from core.constants import ContactInquiryStatus

        if parsed_body.status not in ContactInquiryStatus.values():
            return self.fail(error=str(_("Invalid status")))
        inquiry = self.get_object(pk=parsed_path.pk)
        inquiry.status = parsed_body.status
        inquiry.save(update_fields=["status", "updated_at"])
        return self.ok(self.to_output(inquiry))


class ManagementViewingRequestView(ManagementView, GenericController):
    output_schema = ManagementViewingRequestOutput

    def get_queryset(self):
        from marketplace.models import ViewingRequest

        return ViewingRequest.objects.select_related("listing__property").all()


class ManagementViewingRequestConfirmView(ManagementViewingRequestView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        from core.constants import ViewingRequestStatus

        vr = self.get_object(pk=parsed_path.pk)
        if vr.status == ViewingRequestStatus.CANCELLED:
            return self.fail(
                error=str(_("A cancelled viewing request cannot be confirmed")),
                message=str(_("Invalid status transition")),
            )
        vr.status = ViewingRequestStatus.CONFIRMED
        vr.save(update_fields=["status", "updated_at"])
        return self.ok(self.to_output(vr), status_code=HTTPStatus.OK)


class ManagementViewingRequestCancelView(ManagementViewingRequestView):
    def post(self, parsed_path: Path[DetailPath]) -> dict:
        from core.constants import ViewingRequestStatus

        vr = self.get_object(pk=parsed_path.pk)
        vr.status = ViewingRequestStatus.CANCELLED
        vr.save(update_fields=["status", "updated_at"])
        return self.ok(self.to_output(vr), status_code=HTTPStatus.OK)


def _lead_viewing_qs(tab, search):
    from marketplace.models import ViewingRequest

    qs = ViewingRequest.objects.select_related("listing__property").prefetch_related("listing__property__photos")
    if tab and tab in _LEAD_TAB_VIEWING:
        qs = qs.filter(status__in=_LEAD_TAB_VIEWING[tab])
    if search:
        cond = (
            Q(full_name__icontains=search)
            | Q(phone__icontains=search)
            | Q(email__icontains=search)
            | Q(listing__property__name__icontains=search)
        )
        if search.isdigit():
            cond |= Q(id=int(search))
        qs = qs.filter(cond)
    return qs


def _lead_booking_qs(tab, search):
    from marketplace.models import Booking

    qs = Booking.objects.select_related("property", "tenant", "listing", "reviewed_by").prefetch_related(
        "property__photos"
    )
    if tab and tab in _LEAD_TAB_BOOKING:
        qs = qs.filter(status__in=_LEAD_TAB_BOOKING[tab])
    if search:
        cond = (
            Q(tenant__first_name__icontains=search)
            | Q(tenant__last_name__icontains=search)
            | Q(property__name__icontains=search)
        )
        if search.isdigit():
            cond |= Q(id=int(search))
        qs = qs.filter(cond)
    return qs


class ManagementLeadListView(ManagementView):
    """Unified Leads queue: merges ViewingRequests and Bookings into one list.

    The two sources are serialized independently, merged, then sorted newest-first
    with a stable ``(created_at, type, source_id)`` tie-break, and paginated in
    Python (the framework already materializes every list before paginating).
    """

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        tab = self.request.GET.get("tab")
        lead_type = self.request.GET.get("type")
        search = self.request.GET.get("search")

        rows = []
        if lead_type != "booking":
            rows.extend(
                ManagementLeadOutput.from_viewing(vr, self.request).model_dump(mode="json")
                for vr in _lead_viewing_qs(tab, search)
            )
        if lead_type != "viewing":
            rows.extend(
                ManagementLeadOutput.from_booking(b, self.request).model_dump(mode="json")
                for b in _lead_booking_qs(tab, search)
            )
        rows.sort(key=lambda r: (r["created_at"], r["type"], r["source_id"]), reverse=True)

        if parsed_query.page is not None:
            return self.ok(build_paginated_response(rows, parsed_query.page, parsed_query.per_page))
        return self.ok(rows)


class ManagementLeadStatsView(ManagementView):
    """Tab counts + open total for the Leads queue."""

    def get(self) -> dict:
        lead_type = self.request.GET.get("type")
        search = self.request.GET.get("search")

        counts = {}
        by_type = {"viewing": 0, "booking": 0}
        for tab in ("new", "scheduled", "awaiting", "closed"):
            n = 0
            if lead_type != "booking":
                n += _lead_viewing_qs(tab, search).count()
            if lead_type != "viewing":
                n += _lead_booking_qs(tab, search).count()
            counts[tab] = n
        if lead_type != "booking":
            by_type["viewing"] = _lead_viewing_qs(None, search).count()
        if lead_type != "viewing":
            by_type["booking"] = _lead_booking_qs(None, search).count()
        counts["all"] = by_type["viewing"] + by_type["booking"]

        return self.ok({"counts": counts, "by_type": by_type, "open": counts["new"]})


class ManagementViewingRequestProposeTimeView(ManagementViewingRequestView):
    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementViewingProposeTimeInput]) -> dict:
        from core.constants import ViewingTimeSlot

        vr = self.get_object(pk=parsed_path.pk)
        if vr.status == ViewingRequestStatus.CANCELLED:
            return self.fail(
                error=str(_("Cannot propose a time for a cancelled viewing request")),
                message=str(_("Invalid status transition")),
            )
        if parsed_body.preferred_time is not None and parsed_body.preferred_time not in ViewingTimeSlot.values():
            return self.fail(
                error=str(_("Invalid time slot")),
                message=str(_("Validation error")),
            )
        vr.preferred_date = parsed_body.preferred_date
        vr.preferred_time = parsed_body.preferred_time
        update_fields = ["preferred_date", "preferred_time", "updated_at"]
        # Re-proposing a time to a confirmed lead sends it back to New until the
        # prospect re-confirms the new slot.
        if vr.status == ViewingRequestStatus.CONFIRMED:
            vr.status = ViewingRequestStatus.PENDING
            update_fields.append("status")
        vr.save(update_fields=update_fields)
        return self.ok(self.to_output(vr), status_code=HTTPStatus.OK)


class ManagementVacancyView(ManagementView):
    """Vacancy-cost report: per-property revenue loss from vacant units."""

    def get(self) -> dict:
        from property.models import Property

        from core.constants import PropertyStatus

        vacant = Property.objects.filter(status=PropertyStatus.VACANT).select_related("district")
        rows = []
        total_daily_loss = Decimal("0.00")
        total_accrued_loss = Decimal("0.00")
        for prop in vacant:
            daily = (prop.tenant_charge_price / Decimal("30")).quantize(Decimal("0.01"))
            accrued = (daily * Decimal(prop.vacant_days or 0)).quantize(Decimal("0.01"))
            total_daily_loss += daily
            total_accrued_loss += accrued
            rows.append(
                {
                    "property_id": prop.id,
                    "property_name": prop.name,
                    "district_name": prop.district.name,
                    "tenant_charge_price": str(prop.tenant_charge_price),
                    "currency": prop.tenant_charge_currency,
                    "vacant_since": prop.vacant_since.isoformat() if prop.vacant_since else None,
                    "vacant_days": prop.vacant_days or 0,
                    "daily_loss": str(daily),
                    "accrued_loss": str(accrued),
                }
            )
        return self.ok(
            {
                "vacant_count": len(rows),
                "total_daily_loss": str(total_daily_loss),
                "total_accrued_loss": str(total_accrued_loss),
                "properties": rows,
            }
        )


# Frontend sort values for the Services orders workbench.
_VAS_ORDER_ORDERINGS = {
    "recent": ["-created_at"],
    "oldest": ["created_at"],
    "cost": ["cost", "-id"],
    "-cost": ["-cost", "-id"],
    "scheduled": ["scheduled_for", "-id"],
}


def _vas_completed_recently_q(window_start: date) -> Q:
    """Completed within the window, by ``completed_at`` with ``updated_at`` fallback for legacy rows."""
    return Q(completed_at__date__gte=window_start) | Q(completed_at__isnull=True, updated_at__date__gte=window_start)


class _VASOrderView(ManagementView):
    def get_queryset(self):
        from vas.models import ServiceOrder

        return ServiceOrder.objects.select_related("catalog_item", "tenant", "property").order_by("-created_at")

    def to_output(self, instance):
        from api.v1.vas.schemas import ServiceOrderOutput

        return ServiceOrderOutput.model_validate(instance).model_dump(mode="json")


class ManagementVASOrderListView(_VASOrderView, ListAPIView):
    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.GET
        for field, param in (
            ("status", "status"),
            ("tenant_id", "tenant_id"),
            ("property_id", "property_id"),
            ("catalog_item__service_type", "service_type"),
            ("created_at__date__gte", "date_from"),
            ("created_at__date__lte", "date_to"),
            ("scheduled_for__gte", "scheduled_from"),
            ("scheduled_for__lte", "scheduled_to"),
        ):
            value = params.get(param)
            if value:
                qs = qs.filter(**{field: value})
        search = params.get("search")
        if search:
            cond = (
                Q(catalog_item__name__icontains=search)
                | Q(tenant__first_name__icontains=search)
                | Q(tenant__last_name__icontains=search)
                | Q(property__name__icontains=search)
            )
            if search.isdigit():
                cond |= Q(id=int(search))
            qs = qs.filter(cond)
        order = params.get("order")
        if order in _VAS_ORDER_ORDERINGS:
            qs = qs.order_by(*_VAS_ORDER_ORDERINGS[order])
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return self.list_response(self.get_queryset(), parsed_query)

    def post(self, parsed_body: Body[ManagementServiceOrderCreateInput]) -> dict:
        """Management-initiated order; commission/cashback auto-compute in ServiceOrder.save()."""
        from account.models import User
        from property.models import Property
        from vas.models import ServiceCatalogItem, ServiceOrder

        item = ServiceCatalogItem.objects.filter(pk=parsed_body.catalog_item_id, is_active=True).first()
        if item is None:
            return self.fail(error=str(_("Catalog item not found or inactive")))
        if not User.objects.filter(pk=parsed_body.tenant_id).exists():
            return self.fail(error=str(_("Tenant not found")))
        if not Property.objects.filter(pk=parsed_body.property_id).exists():
            return self.fail(error=str(_("Property not found")))

        order = ServiceOrder.objects.create(
            catalog_item=item,
            tenant_id=parsed_body.tenant_id,
            property_id=parsed_body.property_id,
            lease_id=parsed_body.lease_id,
            cost=parsed_body.cost if parsed_body.cost is not None else item.base_price,
            currency=item.currency,
            scheduled_for=parsed_body.scheduled_for,
            notes=parsed_body.notes,
        )
        return self.ok(self.to_output(order), status_code=HTTPStatus.CREATED)


class ManagementVASOrderDetailView(_VASOrderView, GenericController):
    def get(self, parsed_path: Path[DetailPath]) -> dict:
        return self.ok(self.to_output(self.get_object(pk=parsed_path.pk)))


class ManagementVASOrderStatusView(_VASOrderView, GenericController):
    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ServiceOrderStatusInput]) -> dict:
        from django.utils import timezone
        from notification.services import notify

        from core.constants import NotificationType, VASOrderStatus

        if parsed_body.status not in VASOrderStatus.values():
            return self.fail(error=str(_("Invalid status")))

        order = self.get_object(pk=parsed_path.pk)
        if order.status in (VASOrderStatus.COMPLETED, VASOrderStatus.CANCELLED):
            return self.fail(error=str(_("Invalid status transition")))

        order.status = parsed_body.status
        update_fields = ["status", "updated_at"]
        if parsed_body.status == VASOrderStatus.CANCELLED and parsed_body.reason:
            order.cancellation_reason = parsed_body.reason
            update_fields.append("cancellation_reason")
        if parsed_body.status == VASOrderStatus.COMPLETED:
            order.completed_at = timezone.now()
            update_fields.append("completed_at")
        order.save(update_fields=update_fields)
        notify(
            recipient=order.tenant,
            type=NotificationType.SERVICE_ORDER_STATUS,
            title=str(_("Service order updated")),
            body=str(_("Your %(name)s order is now %(status)s."))
            % {"name": order.catalog_item.name, "status": order.get_status_display()},
            related_object_type="service_order",
            related_object_id=order.id,
        )
        return self.ok(self.to_output(order), status_code=HTTPStatus.OK)


class ManagementVASStatsView(ManagementView):
    """KPI strip + tab counts for the Services workbench."""

    def get(self) -> dict:
        from vas.models import ServiceCatalogItem, ServiceOrder

        from core.constants import VASOrderStatus

        window_start = date.today() - timedelta(days=30)
        base = ServiceOrder.objects.all()
        by_status = {row["status"]: row["n"] for row in base.values("status").annotate(n=Count("id"))}
        completed_30d = base.filter(status=VASOrderStatus.COMPLETED).filter(_vas_completed_recently_q(window_start))
        active_catalog = ServiceCatalogItem.objects.filter(is_active=True)

        return self.ok(
            {
                "new": by_status.get(VASOrderStatus.REQUESTED, 0),
                "revenue_30d": _sum_usd(completed_30d, field="cost"),
                "commission_30d": _sum_usd(completed_30d, field="commission_earned"),
                "catalog_count": active_catalog.count(),
                "partners_count": active_catalog.exclude(partner_name__isnull=True)
                .exclude(partner_name="")
                .values("partner_name")
                .distinct()
                .count(),
                "counts": {
                    "requested": by_status.get(VASOrderStatus.REQUESTED, 0),
                    "confirmed": by_status.get(VASOrderStatus.CONFIRMED, 0),
                    "in_progress": by_status.get(VASOrderStatus.IN_PROGRESS, 0),
                    "completed": by_status.get(VASOrderStatus.COMPLETED, 0),
                    "cancelled": by_status.get(VASOrderStatus.CANCELLED, 0),
                    "all": base.count(),
                },
            }
        )


class ManagementVASPartnersView(ManagementView):
    """Partners tab of the Services workbench: active catalog grouped by partner."""

    def get(self) -> dict:
        from vas.models import ServiceCatalogItem, ServiceOrder

        from core.constants import VASOrderStatus

        window_start = date.today() - timedelta(days=30)
        items = (
            ServiceCatalogItem.objects.filter(is_active=True)
            .exclude(partner_name__isnull=True)
            .exclude(partner_name="")
        )
        partners: dict[str, dict] = {}
        for item in items:
            p = partners.setdefault(
                item.partner_name, {"partner_name": item.partner_name, "service_types": set(), "item_ids": []}
            )
            p["service_types"].add(item.service_type)
            p["item_ids"].append(item.id)

        rows = []
        for p in sorted(partners.values(), key=lambda x: x["partner_name"].lower()):
            orders = ServiceOrder.objects.filter(catalog_item_id__in=p["item_ids"])
            completed_30d = orders.filter(status=VASOrderStatus.COMPLETED).filter(
                _vas_completed_recently_q(window_start)
            )
            rows.append(
                {
                    "partner_name": p["partner_name"],
                    "service_types": sorted(p["service_types"]),
                    "services_count": len(p["item_ids"]),
                    "orders_total": orders.count(),
                    "commission_30d": _sum_usd(completed_30d, field="commission_earned"),
                }
            )
        return self.ok(rows)


class ManagementQueueCountsView(ManagementView):
    """Open-work counts for the sidebar queue badges (leads/onboardings/etc.)."""

    def get(self) -> dict:
        from contract.models import OwnerOnboarding
        from finance.models import Payment, PayoutSchedule
        from finance.utils import overdue_q
        from maintenance.models import ServiceRequest

        from core.constants import OnboardingStatus, PayoutStatus, ServiceRequestStatus

        leads_open = _lead_viewing_qs("new", None).count() + _lead_booking_qs("new", None).count()
        onboardings_open = OwnerOnboarding.objects.filter(
            status__in=[OnboardingStatus.SUBMITTED, OnboardingStatus.OFFER_ACCEPTED]
        ).count()
        maintenance_open = ServiceRequest.objects.filter(status=ServiceRequestStatus.OPEN).count()
        payments_overdue = Payment.objects.filter(overdue_q(date.today())).count()
        payouts_due = PayoutSchedule.objects.filter(status=PayoutStatus.SCHEDULED).count()

        return self.ok(
            {
                "leads": leads_open,
                "onboardings": onboardings_open,
                "maintenance": maintenance_open,
                "payments": payments_overdue,
                "payouts": payouts_due,
            }
        )
