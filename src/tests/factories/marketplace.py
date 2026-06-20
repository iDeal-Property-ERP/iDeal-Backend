import factory
from marketplace.models import Booking, Listing, ViewingRequest

from core.constants import BookingStatus, ViewingRequestStatus

from .account import TenantFactory
from .property import PropertyFactory


class ListingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Listing
        django_get_or_create = ("property",)

    property = factory.SubFactory(PropertyFactory)
    owner_agreement = None
    is_active = True
    is_featured = False
    description = factory.Faker("text", max_nb_chars=300)
    listed_price = 500.00


class ViewingRequestFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ViewingRequest

    listing = factory.SubFactory(ListingFactory)
    full_name = factory.Faker("name")
    phone = "+998901234567"
    email = factory.Faker("email")
    preferred_date = factory.Faker("date_this_year")
    message = factory.Faker("text", max_nb_chars=200)
    status = ViewingRequestStatus.PENDING


class BookingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Booking

    listing = factory.SubFactory(ListingFactory)
    property = factory.LazyAttribute(lambda o: o.listing.property)
    tenant = factory.SubFactory(TenantFactory)
    requested_start_date = factory.Faker("date_this_year")
    requested_end_date = factory.Faker("date_this_year")
    monthly_rent_offer = 550.00
    status = BookingStatus.REQUESTED
    message = factory.Faker("text", max_nb_chars=120)
