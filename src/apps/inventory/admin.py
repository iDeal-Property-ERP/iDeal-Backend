from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from inventory.models import InventoryAct, InventoryActItem, InventoryActPhoto

from core.admin import BaseSoftDeleteModelAdmin


class InventoryActItemInline(admin.TabularInline):
    model = InventoryActItem
    extra = 0


class InventoryActPhotoInline(admin.TabularInline):
    model = InventoryActPhoto
    extra = 0


@admin.register(InventoryAct)
class InventoryActAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "property", "lease", "act_type", "status", "created_by", "created_at", "is_deleted")
    list_filter = ("status", "act_type")
    search_fields = ("property__name", "created_by__first_name", "created_by__last_name")
    ordering = ("-created_at",)
    inlines = (InventoryActItemInline, InventoryActPhotoInline)
    fieldsets = (
        (_("Act Info"), {"fields": ("property", "lease", "act_type", "status", "created_by")}),
        (_("Notes"), {"fields": ("notes",)}),
        (
            _("Acknowledgment"),
            {"fields": ("finalized_at", "acknowledged_by_name", "acknowledged_at", "acknowledgment_note")},
        ),
    )


@admin.register(InventoryActItem)
class InventoryActItemAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "act", "area", "condition", "sort_order", "is_deleted")
    list_filter = ("condition",)
    ordering = ("act", "sort_order")
    fieldsets = ((_("Item Info"), {"fields": ("act", "area", "condition", "notes", "sort_order")}),)


@admin.register(InventoryActPhoto)
class InventoryActPhotoAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "act", "item", "image", "created_at", "is_deleted")
    ordering = ("-created_at",)
    fieldsets = ((_("Photo Info"), {"fields": ("act", "item", "image", "caption")}),)
