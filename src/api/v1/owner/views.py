from decimal import Decimal

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from dmr import Query

from api.v1.owner.schemas import OwnerPropertyOutput
from core.api.permissions import RoleAuth
from core.api.views import BaseController, ListAPIView, ListQuery
from core.constants import PayoutStatus, UserRole


class OwnerPropertyListView(ListAPIView):
    auth = (RoleAuth(UserRole.OWNER),)
    output_schema = OwnerPropertyOutput

    def get_queryset(self):
        from property.models import Property

        user = self.request.user
        return Property.objects.filter(owner=user).select_related("district").order_by("-created_at")

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return super().get(parsed_query)


class OwnerEarningsView(BaseController):
    auth = (RoleAuth(UserRole.OWNER),)

    def get(self) -> dict:
        user = self.request.user
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
    auth = (RoleAuth(UserRole.OWNER),)

    def get(self) -> dict:
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
