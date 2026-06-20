from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic
from pydantic import ConfigDict, model_validator


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
    district_id: int
    district_name: str
    rooms: int
    area_sqm: int
    floor: int
    total_floors: int | None
    owner_id: int
    owner_name: str
    status: str
    tariff: str
    ask_price: Decimal
    ask_currency: str
    owner_guaranteed_price: Decimal
    tenant_charge_price: Decimal
    vacant_since: date | None
    vacant_days: int
    description: str | None
    score: Decimal
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "name": v.name,
            "address": v.address,
            "district_id": v.district_id,
            "district_name": v.district.name,
            "rooms": v.rooms,
            "area_sqm": v.area_sqm,
            "floor": v.floor,
            "total_floors": v.total_floors,
            "owner_id": v.owner_id,
            "owner_name": f"{v.owner.first_name} {v.owner.last_name or ''}".strip(),
            "status": v.status,
            "tariff": v.tariff,
            "ask_price": v.ask_price,
            "ask_currency": v.ask_currency,
            "owner_guaranteed_price": v.owner_guaranteed_price,
            "tenant_charge_price": v.tenant_charge_price,
            "vacant_since": v.vacant_since,
            "vacant_days": v.vacant_days,
            "description": v.description,
            "score": v.score,
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
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
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
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ManagementPaymentOutput(pydantic.BaseModel):
    id: int
    lease_id: int
    tenant_id: int
    tenant_name: str
    paid_by_id: int | None
    amount: Decimal
    currency: str
    payment_date: date
    due_date: date
    status: str
    method: str
    notes: str | None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "lease_id": v.lease_id,
            "tenant_id": v.tenant_id,
            "tenant_name": f"{v.tenant.first_name} {v.tenant.last_name or ''}".strip(),
            "paid_by_id": v.paid_by_id,
            "amount": v.amount,
            "currency": v.currency,
            "payment_date": v.payment_date,
            "due_date": v.due_date,
            "status": v.status,
            "method": v.method,
            "notes": v.notes,
            "created_at": v.created_at,
        }


class ManagementPayoutOutput(pydantic.BaseModel):
    id: int
    owner_agreement_id: int
    owner_id: int
    owner_name: str
    amount: Decimal
    currency: str
    scheduled_date: date
    paid_date: date | None
    status: str
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "owner_agreement_id": v.owner_agreement_id,
            "owner_id": v.owner_id,
            "owner_name": f"{v.owner.first_name} {v.owner.last_name or ''}".strip(),
            "amount": v.amount,
            "currency": v.currency,
            "scheduled_date": v.scheduled_date,
            "paid_date": v.paid_date,
            "status": v.status,
            "created_at": v.created_at,
        }


class ManagementServiceRequestOutput(pydantic.BaseModel):
    id: int
    property_id: int
    property_name: str
    tenant_id: int
    tenant_name: str
    assigned_to_id: int | None
    assigned_to_name: str | None
    title: str
    description: str
    priority: str
    status: str
    cost: Decimal | None
    resolution_notes: str | None
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
            "assigned_to_id": v.assigned_to_id,
            "assigned_to_name": (
                f"{v.assigned_to.first_name} {v.assigned_to.last_name or ''}".strip() if v.assigned_to else None
            ),
            "title": v.title,
            "description": v.description,
            "priority": v.priority,
            "status": v.status,
            "cost": v.cost,
            "resolution_notes": v.resolution_notes,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class ManagementUserUpdateInput(pydantic.BaseModel):
    is_active: bool | None = None
    is_verified: bool | None = None
    role: str | None = None


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


class PnLSummaryOutput(pydantic.BaseModel):
    summary: PnLSummaryCard
    monthly: list[MonthlyPnlRow]
    growth: GrowthData
    investor: InvestorTakeHome


class ManagementOnboardingOutput(pydantic.BaseModel):
    id: int
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


class ManagementViewingRequestOutput(pydantic.BaseModel):
    id: int
    listing_id: int
    property_name: str
    full_name: str
    phone: str
    email: str
    preferred_date: date
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
            "message": v.message,
            "status": v.status,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }
