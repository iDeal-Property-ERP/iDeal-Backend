from contract.models import Lease, OwnerAgreement
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from notification.services import notify

from api.v1.contract.schemas import (
    LeaseCreateInput,
    LeaseOutput,
    LeaseRenewInput,
    LeaseTerminateInput,
    LeaseUpdateInput,
    OwnerAgreementCreateInput,
    OwnerAgreementOutput,
    OwnerAgreementRenewInput,
    OwnerAgreementTerminateInput,
    OwnerAgreementUpdateInput,
)
from core.api.permissions import RoleAuth
from core.api.views import (
    CreateAPIView,
    DetailPath,
    GenericController,
    ListAPIView,
    ListQuery,
    RetrieveAPIView,
)
from core.constants import LeaseStatus, NotificationType, OwnerAgreementStatus, PropertyEngagementType, UserRole


class OwnerAgreementListCreateView(CreateAPIView, ListAPIView):
    model = OwnerAgreement
    output_schema = OwnerAgreementOutput
    create_schema = OwnerAgreementCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return OwnerAgreement.objects.select_related("owner", "property").all()

    def post(self, parsed_body: Body[OwnerAgreementCreateInput]) -> OwnerAgreementOutput:
        from property.models import Property

        prop = Property.objects.filter(pk=parsed_body.property_id).first()
        if prop is None or prop.engagement_type != PropertyEngagementType.MANAGED:
            return self.fail(error=str(_("One-off brokerage properties cannot have owner agreements")))
        return super().post(parsed_body)

    def get(self, parsed_query: Query[ListQuery]) -> list[OwnerAgreementOutput] | Paginated[OwnerAgreementOutput]:
        return super().get(parsed_query)


class OwnerAgreementDetailView(RetrieveAPIView):
    model = OwnerAgreement
    output_schema = OwnerAgreementOutput
    update_schema = OwnerAgreementUpdateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return OwnerAgreement.objects.select_related("owner", "property").all()

    def get(self, parsed_path: Path[DetailPath]) -> OwnerAgreementOutput:
        return super().get(parsed_path)

    def patch(
        self, parsed_path: Path[DetailPath], parsed_body: Body[OwnerAgreementUpdateInput]
    ) -> OwnerAgreementOutput:
        agreement = self.get_object(pk=parsed_path.pk)
        data = parsed_body.model_dump(exclude_unset=True)
        agreement = self.perform_update(agreement, data)
        return self.ok(self.to_output(agreement))


class OwnerAgreementRenewView(GenericController):
    model = OwnerAgreement
    create_schema = OwnerAgreementRenewInput
    output_schema = OwnerAgreementOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return OwnerAgreement.objects.select_related("owner", "property").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[OwnerAgreementRenewInput]) -> OwnerAgreementOutput:
        agreement = self.get_object(pk=parsed_path.pk)
        new_agreement = agreement.renew(
            new_start_date=parsed_body.new_start_date,
            new_end_date=parsed_body.new_end_date,
            commission_rate=parsed_body.commission_rate,
            gross_floor_amount=parsed_body.gross_floor_amount,
            currency=parsed_body.currency,
            payout_day=parsed_body.payout_day,
            agreement_number=parsed_body.agreement_number,
            terms=parsed_body.terms,
        )
        return self.ok(self.to_output(new_agreement))


class OwnerAgreementTerminateView(GenericController):
    model = OwnerAgreement
    create_schema = OwnerAgreementTerminateInput
    output_schema = OwnerAgreementOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return OwnerAgreement.objects.select_related("owner", "property").all()

    def post(
        self, parsed_path: Path[DetailPath], parsed_body: Body[OwnerAgreementTerminateInput]
    ) -> OwnerAgreementOutput:
        agreement = self.get_object(pk=parsed_path.pk)
        if agreement.status == OwnerAgreementStatus.TERMINATED:
            return self.fail(
                error=str(_("This agreement has already been terminated")),
                message=str(_("Invalid status transition")),
            )
        agreement.terminate()
        return self.ok(self.to_output(agreement))


class LeaseListCreateView(CreateAPIView, ListAPIView):
    model = Lease
    output_schema = LeaseOutput
    create_schema = LeaseCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()

    def post(self, parsed_body: Body[LeaseCreateInput]) -> LeaseOutput:
        from property.models import Property

        prop = Property.objects.filter(pk=parsed_body.property_id).first()
        if prop is None or prop.engagement_type != PropertyEngagementType.MANAGED:
            return self.fail(error=str(_("One-off brokerage properties cannot have leases")))
        return super().post(parsed_body)

    def get(self, parsed_query: Query[ListQuery]) -> list[LeaseOutput] | Paginated[LeaseOutput]:
        return super().get(parsed_query)


class LeaseDetailView(RetrieveAPIView):
    model = Lease
    output_schema = LeaseOutput
    update_schema = LeaseUpdateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()

    def get(self, parsed_path: Path[DetailPath]) -> LeaseOutput:
        return super().get(parsed_path)

    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[LeaseUpdateInput]) -> LeaseOutput:
        lease = self.get_object(pk=parsed_path.pk)
        data = parsed_body.model_dump(exclude_unset=True)
        lease = self.perform_update(lease, data)
        return self.ok(self.to_output(lease))


class LeaseRenewView(GenericController):
    model = Lease
    create_schema = LeaseRenewInput
    output_schema = LeaseOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[LeaseRenewInput]) -> LeaseOutput:
        lease = self.get_object(pk=parsed_path.pk)
        new_lease = lease.renew(
            new_start_date=parsed_body.new_start_date,
            new_end_date=parsed_body.new_end_date,
            new_monthly_rent=parsed_body.new_monthly_rent,
            deposit=parsed_body.deposit,
        )
        notify(
            recipient=new_lease.tenant,
            type=NotificationType.LEASE_RENEWAL,
            title=str(_("Lease renewed")),
            body=str(_("Your lease has been renewed through %(end_date)s.")) % {"end_date": new_lease.end_date},
            related_object_type="lease",
            related_object_id=new_lease.id,
        )
        return self.ok(self.to_output(new_lease))


class LeaseTerminateView(GenericController):
    model = Lease
    create_schema = LeaseTerminateInput
    output_schema = LeaseOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[LeaseTerminateInput]) -> LeaseOutput:
        lease = self.get_object(pk=parsed_path.pk)
        if lease.status not in (LeaseStatus.ACTIVE, LeaseStatus.RENEWED):
            return self.fail(
                error=str(_("Only active or renewed leases can be terminated")),
                message=str(_("Invalid status transition")),
            )
        lease = lease.terminate(end_date=parsed_body.end_date, reason=parsed_body.reason)
        return self.ok(self.to_output(lease))
