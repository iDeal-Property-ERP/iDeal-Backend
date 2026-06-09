from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from finance.models import ExchangeRate, Payment, PayoutSchedule

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(Payment)
class PaymentAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "lease", "tenant", "amount", "currency", "status", "method", "payment_date", "is_deleted")
    list_filter = ("status", "method", "currency")
    search_fields = ("tenant__first_name", "tenant__last_name", "lease__property__name")
    ordering = ("-payment_date",)
    fieldsets = (
        (_("Payment Info"), {"fields": ("lease", "tenant", "paid_by", "status", "method")}),
        (_("Amount"), {"fields": ("amount", "currency")}),
        (_("Dates"), {"fields": ("payment_date", "due_date")}),
        (_("Notes"), {"fields": ("notes",)}),
    )


@admin.register(ExchangeRate)
class ExchangeRateAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "currency", "rate", "effective_date", "is_deleted")
    list_filter = ("currency",)
    ordering = ("-effective_date",)
    fieldsets = ((_("Rate Info"), {"fields": ("currency", "rate", "effective_date")}),)


@admin.register(PayoutSchedule)
class PayoutScheduleAdmin(BaseSoftDeleteModelAdmin):
    list_display = ("id", "owner_agreement", "owner", "amount", "currency", "status", "scheduled_date", "is_deleted")
    list_filter = ("status", "currency")
    search_fields = ("owner__first_name", "owner__last_name", "owner_agreement__agreement_number")
    ordering = ("-scheduled_date",)
    fieldsets = (
        (_("Payout Info"), {"fields": ("owner_agreement", "owner", "status")}),
        (_("Amount"), {"fields": ("amount", "currency")}),
        (_("Dates"), {"fields": ("scheduled_date", "paid_date")}),
    )
