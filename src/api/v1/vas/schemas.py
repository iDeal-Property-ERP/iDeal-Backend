from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic

from core.constants import VASServiceType


class ServiceCatalogItemOutput(pydantic.BaseModel):
    id: int
    service_type: str
    name: str
    partner_name: str | None
    description: str | None
    base_price: Decimal
    currency: str
    commission_rate: Decimal
    cashback_rate: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class ServiceCatalogItemCreateInput(pydantic.BaseModel):
    service_type: str = VASServiceType.OTHER
    name: str
    partner_name: str | None = None
    description: str | None = None
    base_price: Decimal
    currency: str = "USD"
    commission_rate: Decimal = Decimal("0.00")
    cashback_rate: Decimal = Decimal("0.00")
    is_active: bool = True


class ServiceCatalogItemUpdateInput(pydantic.BaseModel):
    service_type: str | None = None
    name: str | None = None
    partner_name: str | None = None
    description: str | None = None
    base_price: Decimal | None = None
    currency: str | None = None
    commission_rate: Decimal | None = None
    cashback_rate: Decimal | None = None
    is_active: bool | None = None


class ServiceOrderOutput(pydantic.BaseModel):
    id: int
    catalog_item_id: int
    catalog_item_name: str
    service_type: str
    partner_name: str | None
    tenant_id: int
    tenant_name: str
    property_id: int
    property_name: str
    lease_id: int | None
    status: str
    cost: Decimal
    currency: str
    commission_earned: Decimal
    cashback_amount: Decimal
    scheduled_for: date | None
    notes: str | None
    cancellation_reason: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @pydantic.model_validator(mode="before")
    @classmethod
    def extract(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "catalog_item_id": v.catalog_item_id,
            "catalog_item_name": v.catalog_item.name,
            "service_type": v.catalog_item.service_type,
            "partner_name": v.catalog_item.partner_name,
            "tenant_id": v.tenant_id,
            "tenant_name": f"{v.tenant.first_name} {v.tenant.last_name or ''}".strip(),
            "property_id": v.property_id,
            "property_name": v.property.name,
            "lease_id": v.lease_id,
            "status": v.status,
            "cost": v.cost,
            "currency": v.currency,
            "commission_earned": v.commission_earned,
            "cashback_amount": v.cashback_amount,
            "scheduled_for": v.scheduled_for,
            "notes": v.notes,
            "cancellation_reason": v.cancellation_reason,
            "completed_at": v.completed_at,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class TenantServiceOrderCreateInput(pydantic.BaseModel):
    catalog_item_id: int
    scheduled_for: date | None = None
    notes: str | None = None


class ManagementServiceOrderCreateInput(pydantic.BaseModel):
    """Management-initiated order on behalf of a tenant; cost defaults to the catalog base price."""

    catalog_item_id: int
    tenant_id: int
    property_id: int
    lease_id: int | None = None
    cost: Decimal | None = None
    scheduled_for: date | None = None
    notes: str | None = None


class ServiceOrderStatusInput(pydantic.BaseModel):
    status: str
    # Required by the UI when cancelling; stored as ServiceOrder.cancellation_reason.
    reason: str | None = None
