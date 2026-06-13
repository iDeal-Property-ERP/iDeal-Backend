from __future__ import annotations

import pydantic


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
