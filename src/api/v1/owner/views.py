from decimal import Decimal

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from dmr import Query

from core.api.views import BaseController, ListQuery
from core.constants import PayoutStatus, UserRole


def _build_owner_property(prop):
    return {
        "id": prop.id,
        "name": prop.name,
        "address": prop.address,
        "rooms": prop.rooms,
        "area_sqm": prop.area_sqm,
        "floor": prop.floor,
        "total_floors": prop.total_floors,
        "status": prop.status,
        "tariff": prop.tariff,
        "ask_price": str(prop.ask_price),
        "ask_currency": prop.ask_currency,
        "owner_guaranteed_price": str(prop.owner_guaranteed_price),
        "owner_guaranteed_currency": prop.owner_guaranteed_currency,
        "tenant_charge_price": str(prop.tenant_charge_price),
        "tenant_charge_currency": prop.tenant_charge_currency,
        "vacant_since": prop.vacant_since.isoformat() if prop.vacant_since else None,
        "vacant_days": prop.vacant_days,
        "created_at": prop.created_at.isoformat(),
        "updated_at": prop.updated_at.isoformat(),
    }


class OwnerPropertyListView(BaseController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        user = self.request.user
        if user.role != UserRole.OWNER:
            return self.fail(error=str(_("Only owners can access this endpoint")), status_code=403)
        from property.models import Property

        qs = Property.objects.filter(owner=user).select_related("district").order_by("-created_at")
        items = [_build_owner_property(obj) for obj in qs]
        return self.ok(items)


class OwnerEarningsView(BaseController):
    def get(self) -> dict:
        user = self.request.user
        if user.role != UserRole.OWNER:
            return self.fail(error=str(_("Only owners can access this endpoint")), status_code=403)
        from finance.models import PayoutSchedule
        from property.models import Property

        by_property = PayoutSchedule.objects.filter(owner=user)
        total_guaranteed = Property.objects.filter(owner=user).aggregate(total=Sum("owner_guaranteed_price"))[
            "total"
        ] or Decimal("0.00")
        total_paid = by_property.filter(status=PayoutStatus.PAID).aggregate(total=Sum("amount"))["total"] or Decimal(
            "0.00"
        )
        total_pending = by_property.filter(status=PayoutStatus.SCHEDULED).aggregate(total=Sum("amount"))[
            "total"
        ] or Decimal("0.00")
        return self.ok(
            {
                "total_guaranteed": str(total_guaranteed),
                "total_paid": str(total_paid),
                "total_pending": str(total_pending),
                "currency": "USD",
            }
        )


class OwnerWhyView(BaseController):
    def get(self) -> dict:
        user = self.request.user
        if user.role != UserRole.OWNER:
            return self.fail(error=str(_("Only owners can access this endpoint")), status_code=403)
        return self.ok(
            {
                "title": str(_("Guaranteed Rental Income")),
                "description": str(
                    _(
                        "With iDeal, you receive your rental income every month, "
                        "on time, regardless of whether the property is occupied. "
                        "We handle tenant management, maintenance, and legal compliance."
                    )
                ),
                "benefits": [
                    str(_("Monthly payouts on the 25th of every month")),
                    str(_("No vacancy risk — we guarantee your income")),
                    str(_("Professional tenant screening and management")),
                    str(_("24/7 maintenance support")),
                    str(_("Regular property inspections and reports")),
                ],
            }
        )
