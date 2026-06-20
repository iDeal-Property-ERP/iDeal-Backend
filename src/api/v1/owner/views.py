from decimal import Decimal

from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from dmr import Body, Query

from api.v1.owner.schemas import (
    OwnerOnboardingCreateInput,
    OwnerOnboardingOutput,
    OwnerPropertyOutput,
    PublicOfferOutput,
)
from core.api.permissions import RoleAuth
from core.api.views import BaseController, GenericController, ListAPIView, ListQuery
from core.constants import PayoutStatus, PropertyStatus, UserRole


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


class OwnerPublicOfferView(BaseController):
    auth = (RoleAuth(UserRole.OWNER),)

    def get(self) -> dict:
        from contract.models import PublicOffer

        offer = PublicOffer.get_active()
        if offer is None:
            return self.ok({"id": None, "version": None, "body": None})
        return self.ok(PublicOfferOutput.model_validate(offer).model_dump(mode="json"))


class OwnerOnboardingView(GenericController):
    auth = (RoleAuth(UserRole.OWNER),)
    output_schema = OwnerOnboardingOutput

    def get_queryset(self):
        from contract.models import OwnerOnboarding

        return (
            OwnerOnboarding.objects.filter(owner=self.request.user).select_related("property").order_by("-created_at")
        )

    def get(self, parsed_query: Query[ListQuery]) -> dict:
        return self.list_response(self.get_queryset(), parsed_query)

    def post(self, parsed_body: Body[OwnerOnboardingCreateInput]) -> dict:
        user = self.request.user
        if not parsed_body.accept_offer:
            return self.fail(
                error=str(_("You must accept the public offer to submit a property")),
                status_code=400,
            )

        from contract.models import OwnerOnboarding, PublicOffer
        from property.models import Property

        prop = Property.objects.create(
            name=parsed_body.name,
            address=parsed_body.address,
            district_id=parsed_body.district_id,
            rooms=parsed_body.rooms,
            area_sqm=parsed_body.area_sqm,
            floor=parsed_body.floor,
            total_floors=parsed_body.total_floors,
            owner=user,
            status=PropertyStatus.PENDING_REVIEW,
            description=parsed_body.description,
            ask_price=parsed_body.ask_price,
            ask_currency=parsed_body.ask_currency,
            # Placeholder pricing — management finalizes these at approval.
            owner_guaranteed_price=parsed_body.ask_price,
            owner_guaranteed_currency=parsed_body.ask_currency,
            tenant_charge_price=parsed_body.ask_price,
            tenant_charge_currency=parsed_body.ask_currency,
        )

        onboarding = OwnerOnboarding(owner=user, property=prop)
        onboarding.accept_offer(PublicOffer.get_active())
        onboarding.save()
        return self.ok(self.to_output(onboarding))
