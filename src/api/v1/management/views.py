from datetime import date, timedelta
from decimal import Decimal
from http import HTTPStatus

from django.db.models import Count, F, Q, Sum
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
    ManagementLeaseOutput,
    ManagementOnboardingApproveInput,
    ManagementOnboardingOutput,
    ManagementOnboardingRejectInput,
    ManagementPaymentOutput,
    ManagementPayoutOutput,
    ManagementPropertyOutput,
    ManagementServiceRequestOutput,
    ManagementUserOutput,
    ManagementUserUpdateInput,
    ManagementViewingRequestOutput,
    MonthlyPnlRow,
    PnLSummaryCard,
    PnLSummaryOutput,
    RecentPaymentRow,
)
from api.v1.vas.schemas import ServiceOrderStatusInput
from core.api.permissions import RoleAuth
from core.api.views import BaseController, DetailPath, GenericController, ListAPIView, ListQuery
from core.constants import UserRole


def _d(value):
    return str(value.quantize(Decimal("0.01")))


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
            payments = Payment.objects.filter(status="paid", payment_date__year=current_year, payment_date__month=m)
            payouts = PayoutSchedule.objects.filter(status="paid", paid_date__year=current_year, paid_date__month=m)

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
            growth_actual.append(GrowthPoint(month=month_names[m - 1], revenue=_d(revenue_usd)))

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
                    growth_projected.append(GrowthPoint(month=month_names[proj_month - 1], revenue=_d(last_rev)))

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


class ManagementUserDetailUpdateView(ManagementView, GenericController):
    output_schema = ManagementUserOutput

    def get_queryset(self):
        from account.models import User

        return User.objects.all()

    def get(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        return self.ok(self.to_output(instance))

    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[ManagementUserUpdateInput]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        instance = self.perform_update(instance, parsed_body.model_dump(exclude_unset=True))
        return self.ok(self.to_output(instance))


class ManagementPropertyListView(ManagementView, ListAPIView):
    output_schema = ManagementPropertyOutput

    def get_queryset(self):
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
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class LeaseListView(ManagementView, ListAPIView):
    output_schema = ManagementLeaseOutput

    def get_queryset(self):
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

        if status:
            qs = qs.filter(status=status)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class PaymentListView(ManagementView, ListAPIView):
    output_schema = ManagementPaymentOutput

    def get_queryset(self):
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
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class PayoutListView(ManagementView, ListAPIView):
    output_schema = ManagementPayoutOutput

    def get_queryset(self):
        from finance.models import PayoutSchedule

        qs = PayoutSchedule.objects.select_related("owner").order_by("-scheduled_date")
        status = self.request.GET.get("status")
        owner_id = self.request.GET.get("owner_id")

        if status:
            qs = qs.filter(status=status)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementServiceRequestListView(ManagementView, ListAPIView):
    output_schema = ManagementServiceRequestOutput

    def get_queryset(self):
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
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class ManagementOnboardingListView(ManagementView, ListAPIView):
    output_schema = ManagementOnboardingOutput

    def get_queryset(self):
        from contract.models import OwnerOnboarding

        qs = OwnerOnboarding.objects.select_related("owner", "property").order_by("-created_at")
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        return qs

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


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
        booking = self.get_object(pk=parsed_path.pk)
        try:
            booking.convert_to_lease(
                reviewed_by=self.request.user,
                owner_agreement_id=parsed_body.owner_agreement_id,
                monthly_rent=parsed_body.monthly_rent,
                deposit=parsed_body.deposit,
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


class ManagementVASOrderListView(ManagementView, ListAPIView):
    def get_queryset(self):
        from vas.models import ServiceOrder

        qs = ServiceOrder.objects.select_related("catalog_item", "tenant", "property").order_by("-created_at")
        status = self.request.GET.get("status")
        tenant_id = self.request.GET.get("tenant_id")
        property_id = self.request.GET.get("property_id")
        if status:
            qs = qs.filter(status=status)
        if tenant_id:
            qs = qs.filter(tenant_id=tenant_id)
        if property_id:
            qs = qs.filter(property_id=property_id)
        return qs

    def to_output(self, instance):
        from api.v1.vas.schemas import ServiceOrderOutput

        return ServiceOrderOutput.model_validate(instance).model_dump(mode="json")

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return self.list_response(self.get_queryset(), parsed_query)


class ManagementVASOrderStatusView(ManagementView, GenericController):
    def get_queryset(self):
        from vas.models import ServiceOrder

        return ServiceOrder.objects.select_related("catalog_item", "tenant", "property").all()

    def to_output(self, instance):
        from api.v1.vas.schemas import ServiceOrderOutput

        return ServiceOrderOutput.model_validate(instance).model_dump(mode="json")

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[ServiceOrderStatusInput]) -> dict:
        from notification.services import notify

        from core.constants import NotificationType, VASOrderStatus

        if parsed_body.status not in VASOrderStatus.values():
            return self.fail(error=str(_("Invalid status")))

        order = self.get_object(pk=parsed_path.pk)
        order.status = parsed_body.status
        order.save(update_fields=["status", "updated_at"])
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
