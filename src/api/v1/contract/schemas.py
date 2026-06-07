from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic


class OwnerAgreementOutput(pydantic.BaseModel):
    id: int
    owner_id: int
    property_id: int
    agreement_number: str
    signed_date: date
    start_date: date
    end_date: date
    status: str
    terms: str | None
    commission_rate: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class OwnerAgreementCreateInput(pydantic.BaseModel):
    owner_id: int
    property_id: int
    agreement_number: str
    signed_date: date
    start_date: date
    end_date: date
    status: str = "active"
    terms: str | None = None
    commission_rate: Decimal


class LeaseOutput(pydantic.BaseModel):
    id: int
    property_id: int
    owner_agreement_id: int
    tenant_id: int
    start_date: date
    end_date: date
    monthly_rent: Decimal
    deposit: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class LeaseCreateInput(pydantic.BaseModel):
    property_id: int
    owner_agreement_id: int
    tenant_id: int
    start_date: date
    end_date: date
    monthly_rent: Decimal
    deposit: Decimal
    status: str = "active"


class LeaseRenewInput(pydantic.BaseModel):
    new_start_date: date
    new_end_date: date
    new_monthly_rent: Decimal
    deposit: Decimal | None = None


class LeaseRenewalOutput(pydantic.BaseModel):
    id: int
    previous_lease_id: int
    new_lease_id: int
    renewal_date: date
    new_start_date: date
    new_end_date: date
    new_monthly_rent: Decimal
    created_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)
