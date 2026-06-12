from agent.models import Agent, AgentDeal
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(Agent)
class AgentAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "user", "total_deals", "total_revenue", "commission_rate", "is_active", "is_deleted")
    list_filter = ("is_active",)
    search_fields = ("user__first_name", "user__last_name", "user__username")
    ordering = ("-total_deals", "-total_revenue")
    fieldsets = (
        (_("Agent Info"), {"fields": ("user", "is_active")}),
        (_("Performance"), {"fields": ("total_deals", "total_revenue", "commission_rate")}),
    )
    readonly_fields = ("total_deals", "total_revenue")


@admin.register(AgentDeal)
class AgentDealAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "agent", "property", "deal_date", "rent_amount", "commission_amount", "status", "is_deleted")
    list_filter = ("status", "deal_date")
    search_fields = ("agent__user__first_name", "agent__user__last_name", "property__name")
    ordering = ("-deal_date",)
    fieldsets = (
        (_("Deal Info"), {"fields": ("agent", "property", "deal_date", "status")}),
        (_("Financials"), {"fields": ("rent_amount", "commission_amount")}),
    )
