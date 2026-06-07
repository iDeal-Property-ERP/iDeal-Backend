from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from property.models import District, Property, PropertyPhoto

from core.admin import BaseModelAdmin, BaseSoftDeleteModelAdmin


class PropertyPhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 1
    fields = ("image", "is_primary", "sort_order")


@admin.register(District)
class DistrictAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "name", "city", "is_deleted")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Property)
class PropertyAdmin(BaseSoftDeleteModelAdmin):
    list_display = (
        "id",
        "name",
        "district",
        "owner",
        "status",
        "tariff",
        "rooms",
        "area_sqm",
        "ask_price",
        "is_deleted",
    )
    list_filter = ("status", "tariff", "district")
    search_fields = ("name", "address", "owner__first_name", "owner__last_name")
    ordering = ("-created_at",)
    inlines = [PropertyPhotoInline]
    fieldsets = (
        (_("Location"), {"fields": ("name", "address", "district", "map_lat", "map_lon")}),
        (_("Details"), {"fields": ("rooms", "area_sqm", "floor", "total_floors", "description", "tariff", "score")}),
        (_("Ownership & Status"), {"fields": ("owner", "status", "vacant_since", "vacant_days")}),
        (
            _("Pricing"),
            {
                "fields": (
                    ("ask_price", "ask_currency"),
                    ("owner_guaranteed_price", "owner_guaranteed_currency"),
                    ("tenant_charge_price", "tenant_charge_currency"),
                ),
            },
        ),
    )


@admin.register(PropertyPhoto)
class PropertyPhotoAdmin(BaseModelAdmin):
    list_display = ("id", "property", "is_primary", "sort_order")
    list_filter = ("is_primary",)
    ordering = ("property", "sort_order")
