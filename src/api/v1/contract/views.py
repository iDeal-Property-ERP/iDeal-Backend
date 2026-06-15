from contract.models import Lease, OwnerAgreement
from dmr import Body, Path, Query
from dmr.pagination import Paginated

from api.v1.contract.schemas import (
    LeaseCreateInput,
    LeaseOutput,
    LeaseRenewInput,
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
from core.constants import UserRole


class OwnerAgreementListCreateView(CreateAPIView, ListAPIView):
    model = OwnerAgreement
    output_schema = OwnerAgreementOutput
    create_schema = OwnerAgreementCreateInput
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return OwnerAgreement.objects.select_related("owner", "property").all()

    def post(self, parsed_body: Body[OwnerAgreementCreateInput]) -> OwnerAgreementOutput:
        return super().post(parsed_body)

    def get(
        self, parsed_query: Query[ListQuery]
    ) -> list[OwnerAgreementOutput] | Paginated[OwnerAgreementOutput]:
        return super().get(parsed_query)


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
    auth = (RoleAuth(UserRole.MANAGEMENT),)

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()

    def get(self, parsed_path: Path[DetailPath]) -> LeaseOutput:
        return super().get(parsed_path)


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
        return self.ok(self.to_output(new_lease))
