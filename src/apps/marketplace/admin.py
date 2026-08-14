from django.contrib import admin
from marketplace.models import Booking, ContactInquiry, FaqItem, FavoriteListing, Listing, ViewingRequest

from core.admin import BaseModelAdmin, BaseSoftDeleteModelAdmin


@admin.register(Listing)
class ListingAdmin(BaseSoftDeleteModelAdmin):
    list_display = (
        "id",
        "property",
        "status",
        "is_active",
        "is_featured",
        "monthly_price",
        "minimum_stay",
        "created_at",
        "is_deleted",
    )
    list_filter = ("status", "is_active", "is_featured")
    search_fields = ("property__name",)
    ordering = ("-created_at",)


@admin.register(ViewingRequest)
class ViewingRequestAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "listing", "full_name", "phone", "preferred_date", "preferred_time", "status", "is_deleted")
    list_filter = ("status",)
    search_fields = ("full_name", "phone", "email")
    ordering = ("-created_at",)


@admin.register(ContactInquiry)
class ContactInquiryAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "listing", "full_name", "phone", "status", "created_at", "is_deleted")
    list_filter = ("status",)
    search_fields = ("full_name", "phone", "email")
    ordering = ("-created_at",)


@admin.register(FaqItem)
class FaqItemAdmin(BaseModelAdmin):
    list_display = ("id", "question", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("question", "answer")
    ordering = ("sort_order", "id")


@admin.register(Booking)
class BookingAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "property", "tenant", "status", "requested_start_date", "created_at", "is_deleted")
    list_filter = ("status",)
    search_fields = ("property__name", "tenant__first_name", "tenant__last_name")
    ordering = ("-created_at",)


@admin.register(FavoriteListing)
class FavoriteListingAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "user", "listing", "created_at", "is_deleted")
    list_filter = ("created_at",)
    search_fields = ("user__first_name", "user__last_name", "user__phone", "listing__property__name")
    ordering = ("-created_at",)
