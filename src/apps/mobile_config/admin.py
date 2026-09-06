from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from mobile_config.models import MobileCriticalUpdateRange, MobileHomeBanner, MobileUpdatePolicy
from unfold.admin import TabularInline

from core.admin import BaseModelAdmin


class MobileCriticalUpdateRangeInline(TabularInline):
    model = MobileCriticalUpdateRange
    extra = 1
    fields = ("minimum_version", "maximum_version", "is_active")


@admin.register(MobileUpdatePolicy)
class MobileUpdatePolicyAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "platform",
        "latest_version",
        "store_url",
        "is_active",
        "created_at",
    )
    list_filter = ("platform", "is_active")
    search_fields = ("latest_version", "store_url")
    ordering = ("-created_at",)
    inlines = [MobileCriticalUpdateRangeInline]
    fieldsets = (
        (
            _("Policy Info"),
            {
                "fields": (
                    "platform",
                    "latest_version",
                    "store_url",
                    "is_active",
                )
            },
        ),
    )


@admin.register(MobileCriticalUpdateRange)
class MobileCriticalUpdateRangeAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "policy",
        "minimum_version",
        "maximum_version",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "policy__platform")
    search_fields = ("minimum_version", "maximum_version", "policy__latest_version")
    ordering = ("-created_at",)


@admin.register(MobileHomeBanner)
class MobileHomeBannerAdmin(BaseModelAdmin):
    list_display = (
        "id",
        "title",
        "tag",
        "icon",
        "sort_order",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = (
        "title_en",
        "title_ru",
        "title_uz",
        "description_en",
        "description_ru",
        "description_uz",
    )
    list_editable = ("sort_order", "is_active")
    ordering = ("sort_order", "id")
