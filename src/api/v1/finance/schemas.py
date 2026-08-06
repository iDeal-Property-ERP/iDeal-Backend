from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

import pydantic

from core.constants import Currency, PaymentKind, PaymentMethod, PaymentStatus, PayoutMethod

PositiveAmount = Annotated[Decimal, pydantic.Field(gt=0)]


def _validate_currency(value: str) -> str:
    if value not in Currency.values():
        raise ValueError(f"Unsupported currency '{value}'. Allowed: {', '.join(Currency.values())}.")
    return value


CurrencyStr = Annotated[str, pydantic.AfterValidator(_validate_currency)]


class PaymentOutput(pydantic.BaseModel):
    id: int
    lease_id: int
    tenant_id: int
    paid_by_id: int
    amount: Decimal
    currency: str
    payment_date: date
    due_date: date
    rental_period: date | None
    kind: str
    status: str
    method: str
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class PaymentCreateInput(pydantic.BaseModel):
    lease_id: int
    tenant_id: int
    paid_by_id: int
    amount: PositiveAmount
    currency: CurrencyStr = "USD"
    payment_date: date
    due_date: date
    rental_period: date | None = None
    kind: str = PaymentKind.RENT
    status: str = PaymentStatus.PENDING
    method: str = PaymentMethod.CASH
    gateway_ref: str | None = None
    notes: str | None = None


class PaymentPartialUpdateInput(pydantic.BaseModel):
    amount: Decimal | None = None
    currency: str | None = None
    payment_date: date | None = None
    due_date: date | None = None
    rental_period: date | None = None
    kind: str | None = None
    method: str | None = None
    gateway_ref: str | None = None
    notes: str | None = None


class PaymentMarkPaidInput(pydantic.BaseModel):
    method: str | None = None
    gateway_ref: str | None = None
    payment_date: date | None = None


class PaymentBulkMarkPaidInput(pydantic.BaseModel):
    ids: list[int]
    method: str | None = None


class PaymentBulkActionOutput(pydantic.BaseModel):
    updated: int
    skipped: int


class PaymentRemindInput(pydantic.BaseModel):
    ids: list[int]


class PaymentRemindOutput(pydantic.BaseModel):
    sent: int


class ExchangeRateOutput(pydantic.BaseModel):
    id: int
    currency: str
    rate: Decimal
    effective_date: date
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class ExchangeRateCreateInput(pydantic.BaseModel):
    currency: CurrencyStr
    rate: PositiveAmount
    effective_date: date


class PayoutScheduleOutput(pydantic.BaseModel):
    id: int
    owner_agreement_id: int
    owner_id: int
    settlement_id: int | None
    kind: str
    amount: Decimal
    currency: str
    scheduled_date: date
    paid_date: date | None
    status: str
    status_reason: str | None
    method: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class PayoutScheduleCreateInput(pydantic.BaseModel):
    owner_agreement_id: int
    amount: PositiveAmount
    currency: CurrencyStr = "USD"
    scheduled_date: date
    method: str = PayoutMethod.BANK_TRANSFER


class SettlementOutput(pydantic.BaseModel):
    id: int
    owner_agreement_id: int
    owner_id: int
    period_start: date
    period_end: date
    covered_days: int
    days_in_month: int
    gross_floor_amount: Decimal
    commission_rate: Decimal
    currency: str
    rent_received_amount: Decimal
    settlement_base_amount: Decimal
    commission_amount: Decimal
    owner_payout_amount: Decimal
    ideal_cash_exposure: Decimal
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class SettlementAllocationOutput(pydantic.BaseModel):
    id: int
    payment_id: int
    amount: Decimal
    created_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class PayoutBulkMarkPaidInput(pydantic.BaseModel):
    ids: list[int]


class PayoutBulkActionOutput(pydantic.BaseModel):
    updated: int
    skipped: int


class PayoutHoldInput(pydantic.BaseModel):
    reason: str


class PayoutCancelInput(pydantic.BaseModel):
    reason: str | None = None


class DashboardMetrics(pydantic.BaseModel):
    total_payments: Decimal
    total_payments_uzs: Decimal
    total_payouts: Decimal
    total_payouts_uzs: Decimal
    net_margin: Decimal
    net_margin_uzs: Decimal
    pending_count: int
    pending_amount: Decimal
    overdue_count: int
    overdue_amount: Decimal


class PnLBreakdown(pydantic.BaseModel):
    gross_revenue: Decimal
    gross_revenue_uzs: Decimal
    owner_payouts: Decimal
    owner_payouts_uzs: Decimal
    net_margin: Decimal
    net_margin_uzs: Decimal
    payment_count: int
    tax_estimate: Decimal
    tax_estimate_uzs: Decimal
    cash_collected: Decimal
    contractual_commission: Decimal
    ideal_cash_exposure: Decimal
    net_cash_position: Decimal


class PnLFilter(pydantic.BaseModel):
    year: int | None = None
    month: int | None = None
    start_date: date | None = None
    end_date: date | None = None
