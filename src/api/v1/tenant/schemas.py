from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic
from pydantic import model_validator


class TenantHomeOutput(pydantic.BaseModel):
    lease_id: int
    property_id: int
    property_name: str
    property_address: str
    start_date: date
    end_date: date
    monthly_rent: Decimal
    deposit: Decimal
    status: str
    next_payment_due: date | None
    rent_due: Decimal | None


class TenantPaymentOutput(pydantic.BaseModel):
    id: int
    amount: Decimal
    currency: str
    payment_date: date
    due_date: date
    status: str
    method: str
    notes: str | None
    created_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class TenantPaymentCreateInput(pydantic.BaseModel):
    amount: Decimal | None = None
    method: str = "cash"
    notes: str | None = None


class TenantServiceRequestOutput(pydantic.BaseModel):
    id: int
    property_id: int
    property_name: str
    title: str
    description: str
    priority: str
    status: str
    cost: Decimal | None
    resolution_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def extract_related(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "property_id": v.property_id,
            "property_name": v.property.name,
            "title": v.title,
            "description": v.description,
            "priority": v.priority,
            "status": v.status,
            "cost": v.cost,
            "resolution_notes": v.resolution_notes,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class TenantServiceRequestCreateInput(pydantic.BaseModel):
    property_id: int
    title: str
    description: str
    priority: str = "medium"


class TenantBookingCreateInput(pydantic.BaseModel):
    listing_id: int
    requested_start_date: date
    requested_end_date: date
    monthly_rent_offer: Decimal | None = None
    message: str | None = None


class TenantBookingOutput(pydantic.BaseModel):
    id: int
    listing_id: int
    property_id: int
    property_name: str
    requested_start_date: date
    requested_end_date: date
    monthly_rent_offer: Decimal | None
    status: str
    message: str | None
    converted_lease_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)

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
            "requested_start_date": v.requested_start_date,
            "requested_end_date": v.requested_end_date,
            "monthly_rent_offer": v.monthly_rent_offer,
            "status": v.status,
            "message": v.message,
            "converted_lease_id": v.converted_lease_id,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }
