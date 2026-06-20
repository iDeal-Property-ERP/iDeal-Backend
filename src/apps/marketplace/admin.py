from django.contrib import admin
from marketplace.models import Booking, Listing, ViewingRequest

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(Listing)
class ListingAdmin(BaseSoftDeleteModelAdmin):
    pass


@admin.register(ViewingRequest)
class ViewingRequestAdmin(BaseSoftDeleteModelAdmin):
    pass


@admin.register(Booking)
class BookingAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "property", "tenant", "status", "requested_start_date", "created_at", "is_deleted")
    list_filter = ("status",)
    search_fields = ("property__name", "tenant__first_name", "tenant__last_name")
    ordering = ("-created_at",)
