import pydantic
from contract.models import Lease, OwnerAgreement
from django.utils.translation import gettext_lazy as _
from dmr import Body, Path

from api.v1.contract.schemas import (
    LeaseCreateInput,
    LeaseOutput,
    LeaseRenewInput,
    OwnerAgreementCreateInput,
    OwnerAgreementOutput,
)
from core.api.views import (
    CreateAPIView,
    DetailPath,
    GenericController,
    ListAPIView,
    RetrieveAPIView,
)


class OwnerAgreementListCreateView(CreateAPIView, ListAPIView):
    model = OwnerAgreement
    output_schema = OwnerAgreementOutput
    create_schema = OwnerAgreementCreateInput

    def get_queryset(self):
        return OwnerAgreement.objects.select_related("owner", "property").all()


class LeaseListCreateView(CreateAPIView, ListAPIView):
    model = Lease
    output_schema = LeaseOutput
    create_schema = LeaseCreateInput

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()


class LeaseDetailView(RetrieveAPIView):
    model = Lease
    output_schema = LeaseOutput

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()


class LeaseRenewView(GenericController):
    model = Lease
    create_schema = LeaseRenewInput
    output_schema = LeaseOutput

    def get_queryset(self):
        return Lease.objects.select_related("property", "owner_agreement", "tenant").all()

    def post(self, parsed_path: Path[DetailPath], parsed_body: Body[dict]) -> dict:
        lease = self.get_object(pk=parsed_path.pk)
        try:
            validated = LeaseRenewInput.model_validate(parsed_body)
        except pydantic.ValidationError as err:
            return self.fail(error=err.errors(include_url=False), message=str(_("Validation error")))
        new_lease = lease.renew(
            new_start_date=validated.new_start_date,
            new_end_date=validated.new_end_date,
            new_monthly_rent=validated.new_monthly_rent,
            deposit=validated.deposit,
        )
        return self.ok(self.to_output(new_lease))
