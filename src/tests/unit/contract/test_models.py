import pytest
from contract.models import Lease, LeaseRenewal, OwnerAgreement
from django.db.utils import IntegrityError

from core.constants import LeaseStatus, OwnerAgreementStatus
from tests.factories import LeaseFactory, LeaseRenewalFactory, OwnerAgreementFactory


@pytest.mark.django_db
class TestOwnerAgreementModel:
    def test_create_owner_agreement(self, owner, property_obj):
        ag = OwnerAgreementFactory(owner=owner, property=property_obj)
        assert ag.status == OwnerAgreementStatus.ACTIVE
        assert ag.commission_rate == 10.00
        assert ag.owner == owner
        assert ag.property == property_obj
        assert str(ag) == f"{ag.agreement_number} — {ag.property.name}"

    def test_owner_agreement_soft_delete(self):
        ag = OwnerAgreementFactory()
        ag.delete()
        assert ag.deleted_at is not None
        assert not OwnerAgreement.objects.filter(id=ag.id).exists()

    def test_owner_agreement_unique_agreement_number(self):
        OwnerAgreementFactory(agreement_number="UNIQUE-001")
        with pytest.raises(IntegrityError):
            OwnerAgreementFactory(agreement_number="UNIQUE-001")

    def test_owner_agreement_renew(self, owner, property_obj):
        from datetime import date

        old = OwnerAgreementFactory(
            owner=owner,
            property=property_obj,
            agreement_number="AG-REN-001",
            commission_rate=12.00,
        )
        new = old.renew(new_start_date=date(2027, 1, 1), new_end_date=date(2028, 1, 1))

        old.refresh_from_db()
        assert old.status == OwnerAgreementStatus.EXPIRED
        assert new.id != old.id
        assert new.status == OwnerAgreementStatus.ACTIVE
        assert new.owner == owner
        assert new.property == property_obj
        assert new.commission_rate == old.commission_rate
        assert new.agreement_number == "AG-REN-001-R1"

    def test_owner_agreement_renew_with_overrides(self, owner, property_obj):
        from datetime import date
        from decimal import Decimal

        old = OwnerAgreementFactory(owner=owner, property=property_obj)
        new = old.renew(
            new_start_date=date(2027, 1, 1),
            new_end_date=date(2028, 1, 1),
            commission_rate=Decimal("20.00"),
            agreement_number="AG-CUSTOM-9",
        )
        assert new.agreement_number == "AG-CUSTOM-9"
        assert new.commission_rate == Decimal("20.00")

    def test_owner_agreement_terminate(self):
        ag = OwnerAgreementFactory()
        result = ag.terminate()
        ag.refresh_from_db()
        assert ag.status == OwnerAgreementStatus.TERMINATED
        assert result == ag


@pytest.mark.django_db
class TestLeaseModel:
    def test_create_lease_updates_property_status(self, property_obj, tenant):
        agreement = OwnerAgreementFactory(property=property_obj)
        property_obj.status = "vacant"
        property_obj.save()

        LeaseFactory(
            property=property_obj,
            owner_agreement=agreement,
            tenant=tenant,
        )
        property_obj.refresh_from_db()
        assert property_obj.status == "rented"
        assert property_obj.vacant_since is None
        assert property_obj.vacant_days == 0

    def test_lease_str(self):
        lease = LeaseFactory()
        assert f"Lease #{lease.id}" in str(lease)

    def test_lease_soft_delete(self):
        lease = LeaseFactory()
        lease.delete()
        assert lease.deleted_at is not None
        assert not Lease.objects.filter(id=lease.id).exists()

    def test_lease_status_expired_updates_property(self, property_obj, tenant):
        agreement = OwnerAgreementFactory(property=property_obj)
        lease = LeaseFactory(
            property=property_obj,
            owner_agreement=agreement,
            tenant=tenant,
            status=LeaseStatus.ACTIVE,
        )
        property_obj.refresh_from_db()
        assert property_obj.status == "rented"

        lease.status = LeaseStatus.EXPIRED
        lease.save()
        property_obj.refresh_from_db()
        assert property_obj.status == "vacant"
        assert property_obj.vacant_since is not None

    def test_lease_terminate_updates_property(self, property_obj, tenant):
        from datetime import date

        agreement = OwnerAgreementFactory(property=property_obj)
        lease = LeaseFactory(
            property=property_obj,
            owner_agreement=agreement,
            tenant=tenant,
            status=LeaseStatus.ACTIVE,
        )
        property_obj.refresh_from_db()
        assert property_obj.status == "rented"

        result = lease.terminate(end_date=date(2026, 8, 1))
        lease.refresh_from_db()
        assert lease.status == LeaseStatus.TERMINATED
        assert lease.end_date == date(2026, 8, 1)
        assert result == lease

        property_obj.refresh_from_db()
        assert property_obj.status == "vacant"
        assert property_obj.vacant_since is not None


@pytest.mark.django_db
class TestLeaseRenewalModel:
    def test_renew_creates_new_lease_and_renewal(self, property_obj, tenant):
        agreement = OwnerAgreementFactory(property=property_obj)
        from datetime import date

        old_lease = LeaseFactory(
            property=property_obj,
            owner_agreement=agreement,
            tenant=tenant,
            status=LeaseStatus.ACTIVE,
            monthly_rent=500.00,
        )

        new_lease = old_lease.renew(
            new_start_date=date(2026, 7, 1),
            new_end_date=date(2027, 6, 30),
            new_monthly_rent=550.00,
        )

        old_lease.refresh_from_db()
        assert old_lease.status == LeaseStatus.RENEWED

        assert new_lease.id != old_lease.id
        assert new_lease.status == LeaseStatus.ACTIVE
        assert new_lease.property == property_obj
        assert new_lease.tenant == tenant
        assert new_lease.monthly_rent == 550.00

        renewal = LeaseRenewal.objects.get(previous_lease=old_lease, new_lease=new_lease)
        assert renewal.new_monthly_rent == 550.00

    def test_lease_renewal_soft_delete(self):
        renewal = LeaseRenewalFactory()
        renewal.delete()
        assert renewal.deleted_at is not None
        assert not LeaseRenewal.objects.filter(id=renewal.id).exists()
