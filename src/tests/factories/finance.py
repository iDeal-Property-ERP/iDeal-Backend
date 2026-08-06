import factory
from finance.models import ExchangeRate, Payment, PayoutSchedule

from core.constants import Currency, PaymentKind, PaymentMethod, PaymentStatus, PayoutMethod, PayoutStatus

from .account import OwnerFactory, TenantFactory, UserFactory
from .contract import LeaseFactory, OwnerAgreementFactory


class PaymentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Payment

    lease = factory.SubFactory(LeaseFactory)
    tenant = factory.SubFactory(TenantFactory)
    paid_by = factory.SubFactory(UserFactory)
    amount = 500.00
    currency = Currency.USD
    payment_date = factory.Faker("date_this_year")
    due_date = factory.Faker("date_this_year")
    rental_period = None
    kind = PaymentKind.RENT
    status = PaymentStatus.PENDING
    method = PaymentMethod.CASH
    notes = factory.Faker("text", max_nb_chars=200)


class ExchangeRateFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExchangeRate

    currency = Currency.USD
    rate = 12500.00
    effective_date = factory.Faker("date_this_year")


class PayoutScheduleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PayoutSchedule

    owner_agreement = factory.SubFactory(OwnerAgreementFactory)
    owner = factory.SubFactory(OwnerFactory)
    amount = 380.00
    currency = Currency.USD
    scheduled_date = factory.Faker("date_this_year")
    paid_date = None
    status = PayoutStatus.SCHEDULED
    method = PayoutMethod.BANK_TRANSFER
