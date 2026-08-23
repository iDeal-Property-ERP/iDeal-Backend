from contract.models import Lease

from core.api.views import BaseController


def serialize_mobile_contract(lease: Lease) -> dict:
    property_obj = lease.property
    return {
        "id": lease.id,
        # Lease does not yet have a legal contract number. Keep this as a
        # neutral, stable reference instead of exposing the owner agreement.
        "reference": f"#{lease.id}",
        "property": {
            "id": property_obj.id,
            "title": property_obj.name,
            "address": property_obj.address,
        },
        "start_date": lease.start_date.isoformat(),
        "end_date": lease.end_date.isoformat(),
        "monthly_rent": str(lease.monthly_rent),
        "currency": lease.owner_agreement.currency,
        "status": lease.status,
        "status_display": str(lease.get_status_display()),
        # No lease document is stored yet. Preserve the field for a future
        # document upload/download flow without presenting a fake PDF action.
        "document_url": None,
    }


class MobileContractListView(BaseController):
    def get(self) -> dict:
        leases = (
            Lease.objects.filter(tenant=self.request.user)
            .select_related("property", "owner_agreement")
            .order_by("-start_date", "-created_at")
        )
        return self.ok([serialize_mobile_contract(lease) for lease in leases])
