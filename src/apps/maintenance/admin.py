from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from maintenance.models import ServiceRequest, ServiceRequestComment, ServiceRequestPhoto

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(ServiceRequest)
class ServiceRequestAdmin(BaseSoftDeleteModelAdmin):
    list_display = (
        "id",
        "title",
        "property",
        "tenant",
        "assigned_to",
        "priority",
        "status",
        "cost",
        "created_at",
        "is_deleted",
    )
    list_filter = ("status", "priority")
    search_fields = ("title", "description", "tenant__first_name", "tenant__last_name", "property__name")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Request Info"), {"fields": ("property", "tenant", "assigned_to", "title", "description")}),
        (_("Status"), {"fields": ("status", "priority")}),
        (_("Resolution"), {"fields": ("cost", "cost_bearer", "resolution_notes", "resolved_at")}),
    )


@admin.register(ServiceRequestPhoto)
class ServiceRequestPhotoAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "service_request", "image", "created_at", "is_deleted")
    list_filter = ("service_request__property",)
    search_fields = ("service_request__title",)
    ordering = ("-created_at",)
    fieldsets = ((_("Photo Info"), {"fields": ("service_request", "image")}),)


@admin.register(ServiceRequestComment)
class ServiceRequestCommentAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "service_request", "author", "created_at", "is_deleted")
    list_filter = ("service_request__property",)
    search_fields = ("service_request__title", "body")
    ordering = ("-created_at",)
    fieldsets = ((_("Comment Info"), {"fields": ("service_request", "author", "body")}),)
