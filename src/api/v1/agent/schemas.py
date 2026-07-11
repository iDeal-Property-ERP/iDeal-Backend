from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic
from pydantic import model_validator

from core.constants import AgentDealStatus


class AgentOutput(pydantic.BaseModel):
    id: int
    user_id: int
    user_name: str
    total_deals: int
    total_revenue: Decimal
    commission_rate: Decimal
    is_active: bool
    deals_ytd: int
    pending_commission_total: Decimal | None
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
            "user_id": v.user_id,
            "user_name": f"{v.user.first_name} {v.user.last_name or ''}".strip(),
            "total_deals": v.total_deals,
            "total_revenue": v.total_revenue,
            "commission_rate": v.commission_rate,
            "is_active": v.is_active,
            # Annotated by the agent views' queryset; safe defaults elsewhere
            # (e.g. the create path returns a freshly saved, deal-less agent).
            "deals_ytd": getattr(v, "deals_ytd", 0),
            "pending_commission_total": getattr(v, "pending_commission_total", None),
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class AgentDealOutput(pydantic.BaseModel):
    id: int
    agent_id: int
    property_id: int
    property_name: str
    deal_date: date
    rent_amount: Decimal
    commission_amount: Decimal
    status: str
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
            "agent_id": v.agent_id,
            "property_id": v.property_id,
            "property_name": v.property.name,
            "deal_date": v.deal_date,
            "rent_amount": v.rent_amount,
            "commission_amount": v.commission_amount,
            "status": v.status,
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class AgentDealCreateInput(pydantic.BaseModel):
    property_id: int
    deal_date: date
    rent_amount: Decimal
    status: str = AgentDealStatus.CLOSED


class AgentCreateInput(pydantic.BaseModel):
    user_id: int
    commission_rate: Decimal
    is_active: bool = True


class AgentUpdateInput(pydantic.BaseModel):
    commission_rate: Decimal | None = None
    is_active: bool | None = None
