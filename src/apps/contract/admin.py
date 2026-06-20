from contract.models import Lease, LeaseRenewal, OwnerAgreement, OwnerOnboarding, PublicOffer
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(OwnerAgreement)
class OwnerAgreementAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "agreement_number", "property", "owner", "status", "signed_date", "is_deleted")
    list_filter = ("status",)
    search_fields = ("agreement_number", "property__name", "owner__first_name", "owner__last_name")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Agreement Info"), {"fields": ("agreement_number", "property", "owner", "status")}),
        (_("Dates"), {"fields": ("signed_date", "start_date", "end_date")}),
        (_("Terms & Commission"), {"fields": ("terms", "commission_rate")}),
    )


@admin.register(Lease)
class LeaseAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "property", "tenant", "status", "start_date", "end_date", "monthly_rent", "is_deleted")
    list_filter = ("status",)
    search_fields = ("property__name", "tenant__first_name", "tenant__last_name")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Lease Info"), {"fields": ("property", "owner_agreement", "tenant", "status")}),
        (_("Dates"), {"fields": ("start_date", "end_date")}),
        (_("Finance"), {"fields": ("monthly_rent", "deposit")}),
    )


@admin.register(LeaseRenewal)
class LeaseRenewalAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "previous_lease", "new_lease", "renewal_date", "new_monthly_rent", "is_deleted")
    ordering = ("-renewal_date",)
    fieldsets = (
        (_("Renewal Info"), {"fields": ("previous_lease", "new_lease", "renewal_date")}),
        (_("New Lease Terms"), {"fields": ("new_start_date", "new_end_date", "new_monthly_rent")}),
    )


@admin.register(PublicOffer)
class PublicOfferAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "version", "is_active", "created_at", "is_deleted")
    list_filter = ("is_active",)
    search_fields = ("version",)
    ordering = ("-created_at",)
    fieldsets = ((_("Offer Info"), {"fields": ("version", "is_active", "body")}),)


@admin.register(OwnerOnboarding)
class OwnerOnboardingAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "owner", "property", "status", "offer_accepted_at", "created_at", "is_deleted")
    list_filter = ("status",)
    search_fields = ("owner__first_name", "owner__last_name", "property__name")
    ordering = ("-created_at",)
    fieldsets = (
        (_("Onboarding Info"), {"fields": ("owner", "property", "status")}),
        (_("Offer Acceptance"), {"fields": ("offer_version", "offer_terms_snapshot", "offer_accepted_at")}),
        (_("Review"), {"fields": ("reviewed_by", "review_notes", "generated_agreement")}),
    )
