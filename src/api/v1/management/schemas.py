from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pydantic
from pydantic import ConfigDict, model_validator

# Maintenance SLA windows (hours) per priority. Requests still open past
# created_at + window are flagged as breached.
SLA_HOURS_BY_PRIORITY = {
    "critical": 4,
    "high": 8,
    "medium": 24,
    "low": 72,
}
_SLA_DEFAULT_HOURS = 24


class ManagementUserOutput(pydantic.BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str | None
    patronymic: str | None
    username: str
    phone: str | None
    email: str
    role: str
    is_active: bool
    is_verified: bool
    nationality: str | None
    is_staff: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class ManagementPropertyOutput(pydantic.BaseModel):
    id: int
    name: str
    address: str
    # Nullable: draft properties (Phase 7) are saved partially, so these
    # publish-required fields may be absent until the draft is published.
    district_id: int | None
    district_name: str | None
    rooms: int | None
    area_sqm: int | None
    floor: int | None
    total_floors: int | None
    owner_id: int | None
    owner_name: str | None
    status: str
    tariff: str
    ask_price: Decimal | None
    ask_currency: str
    owner_guaranteed_price: Decimal | None
    tenant_charge_price: Decimal | None
    vacant_since: date | None
    vacant_days: int | None
    map_lat: Decimal | None
    map_lon: Decimal | None
    description: str | None
    score: Decimal
    # Tenant / vacancy enrichment (populated from the active-lease prefetch;
    # None when the view didn't prefetch or the state doesn't apply).
    tenant_name: str | None = None
    tenant_since: date | None = None
    vacancy_loss_per_day: Decimal | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        from core.constants import PropertyStatus

        active_leases = getattr(v, "active_leases", [])
        lease = active_leases[0] if active_leases else None
        tenant_name = None
        tenant_since = None
        if lease is not None and lease.tenant is not None:
            tenant_name = f"{lease.tenant.first_name} {lease.tenant.last_name or ''}".strip()
            tenant_since = lease.start_date

        # Vacancy figures are recomputed live: the stored ``vacant_days`` counter
        # can go stale, so days are derived from ``vacant_since`` each read.
        vacant_days = None
        vacancy_loss_per_day = None
        if v.status == PropertyStatus.VACANT:
            vacant_days = max((date.today() - v.vacant_since).days, 0) if v.vacant_since is not None else v.vacant_days
            base_price = v.owner_guaranteed_price or v.ask_price
            if base_price is not None:
                vacancy_loss_per_day = (base_price / Decimal("30")).quantize(Decimal("0.01"))

        return {
            "id": v.id,
            "name": v.name,
            "address": v.address,
            "district_id": v.district_id,
            "district_name": v.district.name if v.district else None,
            "rooms": v.rooms,
            "area_sqm": v.area_sqm,
            "floor": v.floor,
            "total_floors": v.total_floors,
            "owner_id": v.owner_id,
            "owner_name": (f"{v.owner.first_name} {v.owner.last_name or ''}".strip() if v.owner else None),
            "status": v.status,
            "tariff": v.tariff,
            "ask_price": v.ask_price,
            "ask_currency": v.ask_currency,
            "owner_guaranteed_price": v.owner_guaranteed_price,
            "tenant_charge_price": v.tenant_charge_price,
            "vacant_since": v.vacant_since,
            "vacant_days": vacant_days,
            "map_lat": v.map_lat,
            "map_lon": v.map_lon,
            "description": v.description,
            "score": v.score,
            "tenant_name": tenant_name,
            "tenant_since": tenant_since,
            "vacancy_loss_per_day": vacancy_loss_per_day,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ManagementLeaseOutput(pydantic.BaseModel):
    id: int
    property_id: int
    property_name: str
    tenant_id: int
    tenant_name: str
    owner_agreement_id: int
    start_date: date
    end_date: date
    monthly_rent: Decimal
    deposit: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "property_id": v.property_id,
            "property_name": v.property.name,
            "tenant_id": v.tenant_id,
            "tenant_name": f"{v.tenant.first_name} {v.tenant.last_name or ''}".strip(),
            "owner_agreement_id": v.owner_agreement_id,
            "start_date": v.start_date,
            "end_date": v.end_date,
            "monthly_rent": v.monthly_rent,
            "deposit": v.deposit,
            "status": v.status,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ManagementAgreementOutput(pydantic.BaseModel):
    id: int
    agreement_number: str
    owner_id: int
    owner_name: str
    property_id: int
    property_name: str
    signed_date: date
    start_date: date
    end_date: date
    status: str
    commission_rate: Decimal
    owner_guaranteed_amount: Decimal | None
    tenant_charge_amount: Decimal | None
    margin: Decimal | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        margin = None
        if v.owner_guaranteed_amount is not None and v.tenant_charge_amount is not None:
            margin = v.tenant_charge_amount - v.owner_guaranteed_amount
        return {
            "id": v.id,
            "agreement_number": v.agreement_number,
            "owner_id": v.owner_id,
            "owner_name": f"{v.owner.first_name} {v.owner.last_name or ''}".strip(),
            "property_id": v.property_id,
            "property_name": v.property.name,
            "signed_date": v.signed_date,
            "start_date": v.start_date,
            "end_date": v.end_date,
            "status": v.status,
            "commission_rate": v.commission_rate,
            "owner_guaranteed_amount": v.owner_guaranteed_amount,
            "tenant_charge_amount": v.tenant_charge_amount,
            "margin": margin,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ManagementPaymentOutput(pydantic.BaseModel):
    id: int
    lease_id: int
    tenant_id: int
    tenant_name: str
    paid_by_id: int | None
    paid_by_name: str | None
    property_id: int | None
    property_name: str | None
    amount: Decimal
    currency: str
    payment_date: date
    due_date: date
    status: str
    method: str
    gateway_ref: str | None
    notes: str | None
    linked_payout_id: int | None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        prop = getattr(v.lease, "property", None)
        paid_by = v.paid_by
        # Reverse OneToOne (owner_payout) may not exist for unpaid payments.
        try:
            linked_payout_id = v.owner_payout.id
        except Exception:
            linked_payout_id = None
        return {
            "id": v.id,
            "lease_id": v.lease_id,
            "tenant_id": v.tenant_id,
            "tenant_name": f"{v.tenant.first_name} {v.tenant.last_name or ''}".strip(),
            "paid_by_id": v.paid_by_id,
            "paid_by_name": (f"{paid_by.first_name} {paid_by.last_name or ''}".strip() if paid_by else None),
            "property_id": (prop.id if prop else None),
            "property_name": (prop.name if prop else None),
            "amount": v.amount,
            "currency": v.currency,
            "payment_date": v.payment_date,
            "due_date": v.due_date,
            "status": v.status,
            "method": v.method,
            "gateway_ref": v.gateway_ref,
            "notes": v.notes,
            "linked_payout_id": linked_payout_id,
            "created_at": v.created_at,
        }


class ManagementPayoutOutput(pydantic.BaseModel):
    id: int
    owner_agreement_id: int
    owner_id: int
    owner_name: str
    property_id: int | None
    property_name: str | None
    property_address: str | None
    source_payment_id: int | None
    amount: Decimal
    currency: str
    scheduled_date: date
    paid_date: date | None
    status: str
    status_reason: str | None
    method: str
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        prop = getattr(v.owner_agreement, "property", None)
        return {
            "id": v.id,
            "owner_agreement_id": v.owner_agreement_id,
            "owner_id": v.owner_id,
            "owner_name": f"{v.owner.first_name} {v.owner.last_name or ''}".strip(),
            "property_id": (prop.id if prop else None),
            "property_name": (prop.name if prop else None),
            "property_address": (getattr(prop, "address", None) if prop else None),
            "source_payment_id": v.source_payment_id,
            "amount": v.amount,
            "currency": v.currency,
            "scheduled_date": v.scheduled_date,
            "paid_date": v.paid_date,
            "status": v.status,
            "status_reason": v.status_reason,
            "method": v.method,
            "created_at": v.created_at,
        }


class ManagementServiceRequestOutput(pydantic.BaseModel):
    id: int
    property_id: int
    property_name: str
    tenant_id: int
    tenant_name: str
    tenant_phone: str | None
    assigned_to_id: int | None
    assigned_to_name: str | None
    title: str
    description: str
    priority: str
    status: str
    cost: Decimal | None
    cost_bearer: str | None
    resolution_notes: str | None
    resolved_at: datetime | None
    sla_hours: int
    sla_due_at: datetime
    sla_breached: bool
    photos_count: int
    photo_urls: list[str] = []
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        from django.utils import timezone

        from core.constants import ServiceRequestStatus

        sla_hours = SLA_HOURS_BY_PRIORITY.get(v.priority, _SLA_DEFAULT_HOURS)
        sla_due_at = v.created_at + timedelta(hours=sla_hours)
        # Resolved/cancelled requests are terminal — they can no longer breach.
        sla_breached = (
            v.status not in (ServiceRequestStatus.RESOLVED, ServiceRequestStatus.CANCELLED)
            and timezone.now() > sla_due_at
        )
        return {
            "id": v.id,
            "property_id": v.property_id,
            "property_name": v.property.name,
            "tenant_id": v.tenant_id,
            "tenant_name": f"{v.tenant.first_name} {v.tenant.last_name or ''}".strip(),
            "tenant_phone": (v.tenant.phone if v.tenant else None),
            "assigned_to_id": v.assigned_to_id,
            "assigned_to_name": (
                f"{v.assigned_to.first_name} {v.assigned_to.last_name or ''}".strip() if v.assigned_to else None
            ),
            "title": v.title,
            "description": v.description,
            "priority": v.priority,
            "status": v.status,
            "cost": v.cost,
            "cost_bearer": v.cost_bearer,
            "resolution_notes": v.resolution_notes,
            "resolved_at": v.resolved_at,
            "sla_hours": sla_hours,
            "sla_due_at": sla_due_at,
            "sla_breached": sla_breached,
            "photos_count": v.photos.count(),
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ServiceRequestCommentOutput(pydantic.BaseModel):
    id: int
    author_id: int | None
    author_name: str | None
    body: str
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        author = v.author
        return {
            "id": v.id,
            "author_id": v.author_id,
            "author_name": (f"{author.first_name} {author.last_name or ''}".strip() if author else None),
            "body": v.body,
            "created_at": v.created_at,
        }


class ServiceRequestCommentCreateInput(pydantic.BaseModel):
    body: str


class ManagementUserUpdateInput(pydantic.BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None
    role: str | None = None


class ManagementUserCreateInput(pydantic.BaseModel):
    first_name: str
    last_name: str | None = None
    email: str
    phone: str | None = None
    role: str
    is_active: bool = True
    is_verified: bool = False


class RecentPaymentRow(pydantic.BaseModel):
    id: int
    tenant_name: str
    nationality: str | None
    property_name: str
    amount: str
    status: str


class KpiOccupied(pydantic.BaseModel):
    value: int
    total: int
    change: int


class KpiNetProfit(pydantic.BaseModel):
    value: str
    change: str


class KpiPaymentsReceived(pydantic.BaseModel):
    amount: str
    days: int
    on_time_pct: int


class KpiVacant(pydantic.BaseModel):
    value: int
    loss_per_day: str


class DashboardKPIs(pydantic.BaseModel):
    occupied: KpiOccupied
    net_profit: KpiNetProfit
    payments_received: KpiPaymentsReceived
    vacant: KpiVacant


class DashboardOccupancy(pydantic.BaseModel):
    rate: int
    rented: int
    vacant: int
    maintenance: int


class MaintenanceRequestRow(pydantic.BaseModel):
    id: int
    title: str
    property_name: str
    tenant_name: str
    priority: str
    status: str


class DashboardOutput(pydantic.BaseModel):
    greeting: str
    date: str
    location: str
    total_properties: int
    payment_status: str
    kpi: DashboardKPIs
    recent_payments: list[RecentPaymentRow]
    occupancy: DashboardOccupancy
    maintenance_requests: list[MaintenanceRequestRow]


class PnLSummaryCard(pydantic.BaseModel):
    gross_revenue: str
    owner_payouts: str
    net_profit: str
    tax: str


class MonthlyPnlRow(pydantic.BaseModel):
    month: str
    revenue: str
    owner_payouts: str
    profit: str
    tax: str


class GrowthPoint(pydantic.BaseModel):
    month: str
    revenue: str


class GrowthData(pydantic.BaseModel):
    actual: list[GrowthPoint]
    projected: list[GrowthPoint]


class InvestorTakeHome(pydantic.BaseModel):
    monthly: str
    annual: str
    property_count: int
    scaled_50: str


class PnlBreakdownRow(pydantic.BaseModel):
    source: str
    amount: str
    share: str


class PnlServiceTypeRow(pydantic.BaseModel):
    service_type: str
    amount: str


class PnlBreakdown(pydantic.BaseModel):
    revenue: list[PnlBreakdownRow]
    expenses: list[PnlBreakdownRow]
    vas_by_service_type: list[PnlServiceTypeRow]


class PnLSummaryOutput(pydantic.BaseModel):
    summary: PnLSummaryCard
    monthly: list[MonthlyPnlRow]
    growth: GrowthData
    investor: InvestorTakeHome
    # Phase 6 — additive; None-safe for consumers of the legacy shape.
    year: int | None = None
    currency: str | None = None
    sources: list[str] | None = None
    breakdown: PnlBreakdown | None = None


def _onboarding_number(onboarding) -> str:
    return f"ONB-{onboarding.created_at.year}-{onboarding.id:03d}"


class ManagementOnboardingOutput(pydantic.BaseModel):
    id: int
    number: str
    owner_id: int
    owner_name: str
    property_id: int
    property_name: str
    status: str
    offer_version: str | None
    offer_accepted_at: datetime | None
    review_notes: str | None
    generated_agreement_id: int | None
    ask_price: Decimal
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "number": _onboarding_number(v),
            "owner_id": v.owner_id,
            "owner_name": f"{v.owner.first_name} {v.owner.last_name or ''}".strip(),
            "property_id": v.property_id,
            "property_name": v.property.name,
            "status": v.status,
            "offer_version": v.offer_version,
            "offer_accepted_at": v.offer_accepted_at,
            "review_notes": v.review_notes,
            "generated_agreement_id": v.generated_agreement_id,
            "ask_price": v.property.ask_price,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ManagementOnboardingDetailOutput(pydantic.BaseModel):
    """Rich onboarding payload for the triage detail panel (fetched on select)."""

    id: int
    number: str
    owner_id: int
    owner_name: str
    owner_phone: str | None
    owner_properties_count: int
    property_id: int
    property_name: str
    property_address: str
    district_name: str
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None
    tariff: str
    status: str
    offer_version: str | None
    offer_terms_snapshot: str | None
    offer_accepted_at: datetime | None
    review_notes: str | None
    generated_agreement_id: int | None
    ask_price: Decimal
    ask_currency: str
    market_min: Decimal | None
    market_max: Decimal | None
    market_median: Decimal | None
    suggested_price: Decimal | None
    photos: list[str]
    created_at: datetime
    updated_at: datetime


class ManagementOnboardingRequestInfoInput(pydantic.BaseModel):
    note: str


class ManagementOnboardingApproveInput(pydantic.BaseModel):
    commission_rate: Decimal
    start_date: date
    end_date: date
    agreement_number: str | None = None
    terms: str | None = None
    owner_guaranteed_price: Decimal | None = None
    tenant_charge_price: Decimal | None = None


class ManagementOnboardingRejectInput(pydantic.BaseModel):
    review_notes: str | None = None


class ManagementBookingOutput(pydantic.BaseModel):
    id: int
    listing_id: int
    property_id: int
    property_name: str
    tenant_id: int
    tenant_name: str
    requested_start_date: date
    requested_end_date: date
    monthly_rent_offer: Decimal | None
    status: str
    message: str | None
    converted_lease_id: int | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "listing_id": v.listing_id,
            "property_id": v.property_id,
            "property_name": v.property.name,
            "tenant_id": v.tenant_id,
            "tenant_name": f"{v.tenant.first_name} {v.tenant.last_name or ''}".strip(),
            "requested_start_date": v.requested_start_date,
            "requested_end_date": v.requested_end_date,
            "monthly_rent_offer": v.monthly_rent_offer,
            "status": v.status,
            "message": v.message,
            "converted_lease_id": v.converted_lease_id,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ManagementBookingConvertInput(pydantic.BaseModel):
    owner_agreement_id: int | None = None
    monthly_rent: Decimal | None = None
    deposit: Decimal | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("End date must be after the start date")
        return self


class ManagementInquiryOutput(pydantic.BaseModel):
    id: int
    listing_id: int | None
    full_name: str
    phone: str
    email: str | None
    message: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class ManagementInquiryStatusInput(pydantic.BaseModel):
    status: str


class ManagementViewingRequestOutput(pydantic.BaseModel):
    id: int
    listing_id: int
    property_name: str
    full_name: str
    phone: str
    email: str | None
    preferred_date: date
    preferred_time: str | None
    message: str | None
    status: str
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        listing = v.listing
        return {
            "id": v.id,
            "listing_id": v.listing_id,
            "property_name": listing.property.name if listing else "",
            "full_name": v.full_name,
            "phone": v.phone,
            "email": v.email,
            "preferred_date": v.preferred_date,
            "preferred_time": v.preferred_time,
            "message": v.message,
            "status": v.status,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ManagementViewingProposeTimeInput(pydantic.BaseModel):
    preferred_date: date
    preferred_time: str | None = None


class ManagementLeadOutput(pydantic.BaseModel):
    """A unified lead row merging a ViewingRequest or a Booking.

    ``id`` is a composite string (``v-{pk}`` / ``b-{pk}``) so the two sources can
    share one list without pk collisions; ``source_id`` is the underlying pk.
    """

    id: str
    type: str  # "viewing" | "booking"
    source_id: int
    status: str
    name: str
    phone: str | None
    email: str | None
    listing_id: int | None
    property_id: int | None
    property_name: str
    property_address: str | None
    property_status: str | None
    property_rooms: int | None
    property_area_sqm: int | None
    property_floor: int | None
    property_photo_url: str | None
    listing_price: Decimal | None
    currency: str | None
    preferred_date: date | None
    preferred_time: str | None
    requested_start_date: date | None
    requested_end_date: date | None
    monthly_rent_offer: Decimal | None
    message: str | None
    reviewed_by_name: str | None
    converted_lease_id: int | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def _photo_url(prop, request):
        photo = prop.photos.all().order_by("-is_primary", "sort_order", "id").first() if prop else None
        if photo is None:
            return None
        url = photo.image.url
        return request.build_absolute_uri(url) if request is not None else url

    @classmethod
    def from_viewing(cls, vr, request=None):
        listing = vr.listing
        prop = listing.property if listing else None
        return cls.model_validate(
            {
                "id": f"v-{vr.id}",
                "type": "viewing",
                "source_id": vr.id,
                "status": vr.status,
                "name": vr.full_name,
                "phone": vr.phone,
                "email": vr.email,
                "listing_id": vr.listing_id,
                "property_id": (prop.id if prop else None),
                "property_name": (prop.name if prop else ""),
                "property_address": (prop.address if prop else None),
                "property_status": (prop.status if prop else None),
                "property_rooms": (prop.rooms if prop else None),
                "property_area_sqm": (prop.area_sqm if prop else None),
                "property_floor": (prop.floor if prop else None),
                "property_photo_url": cls._photo_url(prop, request),
                "listing_price": (listing.monthly_price or listing.listed_price) if listing else None,
                "currency": (listing.currency if listing else None),
                "preferred_date": vr.preferred_date,
                "preferred_time": vr.preferred_time,
                "requested_start_date": None,
                "requested_end_date": None,
                "monthly_rent_offer": None,
                "message": vr.message,
                "reviewed_by_name": None,
                "converted_lease_id": None,
                "created_at": vr.created_at,
                "updated_at": vr.updated_at,
            }
        )

    @classmethod
    def from_booking(cls, b, request=None):
        prop = b.property
        listing = b.listing
        tenant = b.tenant
        reviewer = b.reviewed_by
        return cls.model_validate(
            {
                "id": f"b-{b.id}",
                "type": "booking",
                "source_id": b.id,
                "status": b.status,
                "name": f"{tenant.first_name} {tenant.last_name or ''}".strip(),
                "phone": getattr(tenant, "phone", None),
                "email": tenant.email,
                "listing_id": b.listing_id,
                "property_id": (prop.id if prop else None),
                "property_name": (prop.name if prop else ""),
                "property_address": (prop.address if prop else None),
                "property_status": (prop.status if prop else None),
                "property_rooms": (prop.rooms if prop else None),
                "property_area_sqm": (prop.area_sqm if prop else None),
                "property_floor": (prop.floor if prop else None),
                "property_photo_url": cls._photo_url(prop, request),
                "listing_price": (listing.monthly_price or listing.listed_price) if listing else None,
                "currency": (listing.currency if listing else None),
                "preferred_date": None,
                "preferred_time": None,
                "requested_start_date": b.requested_start_date,
                "requested_end_date": b.requested_end_date,
                "monthly_rent_offer": b.monthly_rent_offer,
                "message": b.message,
                "reviewed_by_name": (f"{reviewer.first_name} {reviewer.last_name or ''}".strip() if reviewer else None),
                "converted_lease_id": b.converted_lease_id,
                "created_at": b.created_at,
                "updated_at": b.updated_at,
            }
        )
