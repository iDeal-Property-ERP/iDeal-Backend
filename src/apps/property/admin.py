from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from property.models import Amenity, District, Property, PropertyPhoto

from core.admin import BaseModelAdmin, BaseSoftDeleteModelAdmin


class PropertyPhotoInline(admin.TabularInline):
    model = PropertyPhoto
    extra = 1
    fields = ("image", "caption", "is_primary", "sort_order")


@admin.register(District)
class DistrictAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "name", "city", "is_deleted")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Amenity)
class AmenityAdmin(BaseModelAdmin):
    list_display = ("id", "name", "slug", "icon", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")
    prepopulated_fields = {"slug": ("name",)}


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
    list_filter = ("status", "tariff", "property_type", "furnishing", "is_verified", "district")
    search_fields = ("name", "address", "owner__first_name", "owner__last_name")
    ordering = ("-created_at",)
    inlines = [PropertyPhotoInline]
    filter_horizontal = ("amenities",)
    fieldsets = (
        (_("Location"), {"fields": ("name", "address", "district", "map_lat", "map_lon")}),
        (
            _("Details"),
            {
                "fields": (
                    "property_type",
                    ("rooms",),
                    ("area_sqm", "floor", "total_floors"),
                    "furnishing",
                    "amenities",
                    "description",
                    "tariff",
                    "score",
                ),
            },
        ),
        (
            _("Ownership & Status"),
            {
                "fields": (
                    "owner",
                    "status",
                    ("is_verified", "verified_at", "verified_by"),
                    "vacant_since",
                    "vacant_days",
                )
            },
        ),
        (
            _("Pricing"),
            {
                "fields": (
                    ("ask_price", "ask_currency"),
                    ("owner_guaranteed_price", "owner_guaranteed_currency"),
                    ("tenant_charge_price", "tenant_charge_currency"),
                    ("deposit_amount", "deposit_currency"),
                ),
            },
        ),
    )


@admin.register(PropertyPhoto)
class PropertyPhotoAdmin(BaseModelAdmin):
    list_display = ("id", "property", "caption", "is_primary", "sort_order")
    list_filter = ("is_primary",)
    search_fields = ("property__name", "caption")
    ordering = ("property", "sort_order")
