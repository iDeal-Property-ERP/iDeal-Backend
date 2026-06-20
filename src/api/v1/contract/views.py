from contract.models import Lease, OwnerAgreement
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path, Query
from dmr.pagination import Paginated
from notification.services import notify

from api.v1.contract.schemas import (
    LeaseCreateInput,
    LeaseOutput,
    LeaseRenewInput,
    LeaseUpdateInput,
    OwnerAgreementCreateInput,
    OwnerAgreementOutput,
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
from core.constants import NotificationType, UserRole


class OwnerAgreementListCreateView(CreateAPIView, ListAPIView):
    model = OwnerAgreement
    output_schema = OwnerAgreementOutput
    create_schema = OwnerAgreementCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return OwnerAgreement.objects.select_related("owner", "property").all()

    def post(self, parsed_body: Body[OwnerAgreementCreateInput]) -> OwnerAgreementOutput:
        return super().post(parsed_body)

    def get(self, parsed_query: Query[ListQuery]) -> list[OwnerAgreementOutput] | Paginated[OwnerAgreementOutput]:
        return super().get(parsed_query)


class OwnerAgreementDetailView(RetrieveAPIView):
    model = OwnerAgreement
    output_schema = OwnerAgreementOutput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return OwnerAgreement.objects.select_related("owner", "property").all()

    def get(self, parsed_path: Path[DetailPath]) -> OwnerAgreementOutput:
        return super().get(parsed_path)


class LeaseListCreateView(CreateAPIView, ListAPIView):
    model = Lease
    output_schema = LeaseOutput
    create_schema = LeaseCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()

    def post(self, parsed_body: Body[LeaseCreateInput]) -> LeaseOutput:
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
