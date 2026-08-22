import pytest
from marketplace.services.listings import ListingFilters, apply_listing_filters, published_listings_queryset
from property.models import Amenity

from core.constants import PropertyStatus
from tests.factories import DistrictFactory, ListingFactory, PropertyFactory

pytestmark = pytest.mark.django_db


def _listing(**property_kwargs):
    return PropertyFactory(status=PropertyStatus.VACANT, **property_kwargs).listing


def _set_prices(listing, price):
    listing.monthly_price = price
    listing.listed_price = price
    listing.save(update_fields=["monthly_price", "listed_price", "updated_at"])


def test_vacancy_branch_excludes_non_vacant_properties():
    vacant = _listing()
    rented_property = PropertyFactory(status=PropertyStatus.RENTED)
    rented = ListingFactory(property=rented_property)

    result_ids = set(
        apply_listing_filters(published_listings_queryset(), ListingFilters()).values_list("id", flat=True)
    )

    assert vacant.id in result_ids
    assert rented.id not in result_ids


def test_scalar_filters_are_applied():
    district = DistrictFactory(name="Listing Filter District")
    matching = _listing(district=district, rooms=3)
    other = _listing(rooms=1)
    _set_prices(matching, 900)
    _set_prices(other, 300)

    filtered = apply_listing_filters(
        published_listings_queryset(),
        ListingFilters(district_id=district.id, rooms_min=3, price_min=800),
    )

    assert list(filtered.values_list("id", flat=True)) == [matching.id]


def test_amenities_use_an_and_match():
    wifi, _ = Amenity.objects.get_or_create(slug="unit-wifi", defaults={"name": "Wi-Fi"})
    parking, _ = Amenity.objects.get_or_create(slug="unit-parking", defaults={"name": "Parking"})
    matching = _listing()
    partial = _listing()
    matching.property.amenities.set([wifi, parking])
    partial.property.amenities.set([wifi])

    filtered = apply_listing_filters(
        published_listings_queryset(),
        ListingFilters(amenities="unit-wifi,unit-parking"),
    )

    assert list(filtered.values_list("id", flat=True)) == [matching.id]


def test_each_sort_ordering_is_applied():
    cheap = _listing()
    middle = _listing()
    expensive = _listing()
    _set_prices(cheap, 300)
    _set_prices(middle, 700)
    _set_prices(expensive, 1200)
    expensive.is_featured = True
    expensive.save(update_fields=["is_featured", "updated_at"])

    price_asc = apply_listing_filters(published_listings_queryset(), ListingFilters(sort="price_asc")).values_list(
        "id", flat=True
    )
    price_desc = apply_listing_filters(published_listings_queryset(), ListingFilters(sort="price_desc")).values_list(
        "id", flat=True
    )
    newest = apply_listing_filters(published_listings_queryset(), ListingFilters(sort="newest")).values_list(
        "id", flat=True
    )

    assert list(price_asc)[:3] == [cheap.id, middle.id, expensive.id]
    assert list(price_desc)[:3] == [expensive.id, middle.id, cheap.id]
    assert list(newest)[0] == expensive.id


def test_score_sort_ordering_is_applied():
    low_score = _listing()
    mid_score = _listing()
    high_score = _listing()

    low_score.property.score = 3.5
    low_score.property.save(update_fields=["score", "updated_at"])

    mid_score.property.score = 7.8
    mid_score.property.save(update_fields=["score", "updated_at"])

    high_score.property.score = 9.4
    high_score.property.save(update_fields=["score", "updated_at"])

    score_desc = apply_listing_filters(published_listings_queryset(), ListingFilters(sort="score_desc")).values_list(
        "id", flat=True
    )
    rating_desc = apply_listing_filters(published_listings_queryset(), ListingFilters(sort="rating_desc")).values_list(
        "id", flat=True
    )

    assert list(score_desc)[:3] == [high_score.id, mid_score.id, low_score.id]
    assert list(rating_desc)[:3] == [high_score.id, mid_score.id, low_score.id]
