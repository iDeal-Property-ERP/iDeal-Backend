from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pydantic

from core.constants import ServiceRequestPriority


class ServiceRequestOutput(pydantic.BaseModel):
    id: int
    property_id: int
    tenant_id: int
    assigned_to_id: int | None
    title: str
    description: str
    priority: str
    status: str
    cost: Decimal | None
    resolution_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class ServiceRequestCreateInput(pydantic.BaseModel):
    property_id: int
    tenant_id: int
    title: str
    description: str
    priority: str = ServiceRequestPriority.MEDIUM


class ServiceRequestUpdateInput(pydantic.BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | None = None


class ServiceRequestAssignInput(pydantic.BaseModel):
    assigned_to_id: int


class ServiceRequestResolveInput(pydantic.BaseModel):
    cost: Decimal
    resolution_notes: str
    cost_bearer: str | None = None
