from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic

from core.constants import AgentDealStatus


class AgentOutput(pydantic.BaseModel):
    id: int
    user_id: int
    total_deals: int
    total_revenue: Decimal
    commission_rate: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class AgentDealOutput(pydantic.BaseModel):
    id: int
    agent_id: int
    property_id: int
    deal_date: date
    rent_amount: Decimal
    commission_amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class AgentDealCreateInput(pydantic.BaseModel):
    property_id: int
    deal_date: date
    rent_amount: Decimal
    status: str = AgentDealStatus.CLOSED
