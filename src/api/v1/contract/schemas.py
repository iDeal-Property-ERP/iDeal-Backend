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
    gross_floor_amount: Decimal
    currency: str
    payout_day: int
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
    gross_floor_amount: Decimal = Decimal("0.00")
    currency: str = "USD"
    payout_day: int = pydantic.Field(default=25, ge=1, le=31)


class OwnerAgreementUpdateInput(pydantic.BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    commission_rate: Decimal | None = None
    gross_floor_amount: Decimal | None = None
    currency: str | None = None
    payout_day: int | None = pydantic.Field(default=None, ge=1, le=31)
    terms: str | None = None
    status: str | None = None


class OwnerAgreementRenewInput(pydantic.BaseModel):
    new_start_date: date
    new_end_date: date
    commission_rate: Decimal | None = None
    gross_floor_amount: Decimal | None = None
    currency: str | None = None
    payout_day: int | None = pydantic.Field(default=None, ge=1, le=31)
    agreement_number: str | None = None
    terms: str | None = None


class OwnerAgreementTerminateInput(pydantic.BaseModel):
    reason: str | None = None


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


class LeaseUpdateInput(pydantic.BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    monthly_rent: Decimal | None = None
    deposit: Decimal | None = None
    status: str | None = None


class LeaseRenewInput(pydantic.BaseModel):
    new_start_date: date
    new_end_date: date
    new_monthly_rent: Decimal
    deposit: Decimal | None = None


class LeaseTerminateInput(pydantic.BaseModel):
    end_date: date | None = None
    reason: str | None = None


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
