from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pydantic

from core.constants import PaymentMethod, PaymentStatus


class PaymentOutput(pydantic.BaseModel):
    id: int
    lease_id: int
    tenant_id: int
    paid_by_id: int
    amount: Decimal
    currency: str
    payment_date: date
    due_date: date
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
    amount: Decimal
    currency: str = "USD"
    payment_date: date
    due_date: date
    status: str = PaymentStatus.PENDING
    method: str = PaymentMethod.CASH
    notes: str | None = None


class PaymentPartialUpdateInput(pydantic.BaseModel):
    amount: Decimal | None = None
    currency: str | None = None
    payment_date: date | None = None
    due_date: date | None = None
    method: str | None = None
    notes: str | None = None


class ExchangeRateOutput(pydantic.BaseModel):
    id: int
    currency: str
    rate: Decimal
    effective_date: date
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


class ExchangeRateCreateInput(pydantic.BaseModel):
    currency: str
    rate: Decimal
    effective_date: date


class PayoutScheduleOutput(pydantic.BaseModel):
    id: int
    owner_agreement_id: int
    owner_id: int
    amount: Decimal
    currency: str
    scheduled_date: date
    paid_date: date | None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)


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


class PnLFilter(pydantic.BaseModel):
    year: int | None = None
    month: int | None = None
