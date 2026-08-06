import factory
from contract.models import Lease, LeaseRenewal, OwnerAgreement, OwnerOnboarding, PublicOffer

from core.constants import LeaseStatus, OnboardingStatus, OwnerAgreementStatus

from .account import OwnerFactory, TenantFactory
from .property import PropertyFactory


class OwnerAgreementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OwnerAgreement

    owner = factory.SubFactory(OwnerFactory)
    property = factory.SubFactory(PropertyFactory)
    agreement_number = factory.Sequence(lambda n: f"AG-{n:05d}")
    signed_date = factory.Faker("date_this_year")
    start_date = factory.Faker("date_this_year")
    end_date = factory.Faker("date_this_year")
    status = OwnerAgreementStatus.ACTIVE
    terms = factory.Faker("text", max_nb_chars=200)
    commission_rate = 10.00
    gross_floor_amount = 500.00
    currency = "USD"
    payout_day = 25


class LeaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Lease

    property = factory.SubFactory(PropertyFactory)
    owner_agreement = factory.SubFactory(OwnerAgreementFactory)
    tenant = factory.SubFactory(TenantFactory)
    start_date = factory.Faker("date_this_year")
    end_date = factory.Faker("date_this_year")
    monthly_rent = 500.00
    deposit = 500.00
    status = LeaseStatus.ACTIVE


class LeaseRenewalFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LeaseRenewal

    previous_lease = factory.SubFactory(LeaseFactory)
    new_lease = factory.SubFactory(LeaseFactory)
    renewal_date = factory.Faker("date_this_year")
    new_start_date = factory.Faker("date_this_year")
    new_end_date = factory.Faker("date_this_year")
    new_monthly_rent = 550.00


class PublicOfferFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PublicOffer

    version = factory.Sequence(lambda n: f"v{n}")
    body = factory.Faker("text", max_nb_chars=500)
    is_active = True


class OwnerOnboardingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = OwnerOnboarding

    owner = factory.SubFactory(OwnerFactory)
    property = factory.SubFactory(PropertyFactory)
    status = OnboardingStatus.SUBMITTED
