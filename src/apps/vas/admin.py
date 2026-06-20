from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from vas.models import ServiceCatalogItem, ServiceOrder

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(ServiceCatalogItem)
class ServiceCatalogItemAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "name", "service_type", "partner_name", "base_price", "is_active", "is_deleted")
    list_filter = ("service_type", "is_active")
    search_fields = ("name", "partner_name")
    ordering = ("service_type", "name")
    fieldsets = (
        (_("Service Info"), {"fields": ("service_type", "name", "partner_name", "description", "is_active")}),
        (_("Pricing"), {"fields": ("base_price", "currency", "commission_rate", "cashback_rate")}),
    )


@admin.register(ServiceOrder)
class ServiceOrderAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "catalog_item", "tenant", "property", "status", "cost", "commission_earned", "is_deleted")
    list_filter = ("status",)
    search_fields = ("catalog_item__name", "tenant__first_name", "tenant__last_name", "property__name")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Order Info"), {"fields": ("catalog_item", "tenant", "property", "lease", "status")}),
        (_("Pricing"), {"fields": ("cost", "currency", "commission_earned", "cashback_amount")}),
        (_("Scheduling"), {"fields": ("scheduled_for", "notes")}),
    )
