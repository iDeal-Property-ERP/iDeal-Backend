import pytest
from django.db import IntegrityError, models
from marketplace.models import FavoriteListing, Listing, ViewingRequest

from core.constants import PropertyStatus, ViewingRequestStatus
from tests.factories import (
    DistrictFactory,
    FavoriteListingFactory,
    OwnerFactory,
    PropertyFactory,
    TenantFactory,
    ViewingRequestFactory,
)


def _make_vacant_listing(**listing_kwargs):
    prop = PropertyFactory(status=PropertyStatus.VACANT)
    listing = prop.listing
    for k, v in listing_kwargs.items():
        setattr(listing, k, v)
    if listing_kwargs:
        listing.save()
    return listing


def _make_vacant_listing_with_agreement():
    from tests.factories import OwnerAgreementFactory

    prop = PropertyFactory(status=PropertyStatus.VACANT)
    agreement = OwnerAgreementFactory(property=prop, owner=prop.owner)
    listing = prop.listing
    listing.owner_agreement = agreement
    listing.save(update_fields=["owner_agreement", "updated_at"])
    return listing


@pytest.mark.django_db
class TestListingModel:
    def test_create_listing(self):
        listing = _make_vacant_listing()
        assert listing.id is not None
        assert listing.is_active is True
        assert listing.property is not None

    def test_listing_deactivation(self):
        listing = _make_vacant_listing()
        listing.is_active = False
        listing.save(update_fields=["is_active", "updated_at"])
        listing.refresh_from_db()
        assert listing.is_active is False

    def test_listing_str(self):
        listing = _make_vacant_listing()
        assert str(listing) == f"Listing #{listing.id} — {listing.property.name}"

    def test_soft_delete_listing(self):
        listing = _make_vacant_listing()
        listing.delete()
        assert Listing.objects.filter(pk=listing.pk).count() == 0
        assert Listing.global_objects.filter(pk=listing.pk).count() == 1

    def test_listing_featured(self):
        listing = _make_vacant_listing(is_featured=True, listed_price=600.00)
        assert listing.is_featured is True

    def test_listing_with_owner_agreement(self):
        listing = _make_vacant_listing_with_agreement()
        assert listing.owner_agreement is not None

    def test_listing_without_owner_agreement(self):
        listing = _make_vacant_listing()
        assert listing.owner_agreement is None


@pytest.mark.django_db
class TestViewingRequestModel:
    def test_create_viewing_request(self):
        listing = _make_vacant_listing()
        vr = ViewingRequestFactory(listing=listing)
        assert vr.id is not None
        assert vr.status == ViewingRequestStatus.PENDING

    def test_viewing_request_status_choices(self):
        listing = _make_vacant_listing()
        vr = ViewingRequestFactory(listing=listing)
        vr.status = ViewingRequestStatus.CONFIRMED
        vr.save(update_fields=["status", "updated_at"])
        vr.refresh_from_db()
        assert vr.status == ViewingRequestStatus.CONFIRMED

    def test_viewing_request_str(self):
        listing = _make_vacant_listing()
        vr = ViewingRequestFactory(listing=listing)
        expected = f"Viewing #{vr.id} — {vr.full_name} ({vr.get_status_display()})"
        assert str(vr) == expected

    def test_soft_delete_viewing_request(self):
        listing = _make_vacant_listing()
        vr = ViewingRequestFactory(listing=listing)
        vr.delete()
        assert ViewingRequest.objects.filter(pk=vr.pk).count() == 0
        assert ViewingRequest.global_objects.filter(pk=vr.pk).count() == 1

    def test_viewing_request_optional_message(self):
        listing = _make_vacant_listing()
        vr = ViewingRequestFactory(listing=listing, message=None)
        assert vr.message is None

        vr2 = ViewingRequestFactory(listing=listing, message="I want to see the apartment")
        assert vr2.message == "I want to see the apartment"


@pytest.mark.django_db
class TestFavoriteListingModel:
    def test_active_constraint_and_indexes_match_account_listing_semantics(self):
        constraint = next(
            constraint
            for constraint in FavoriteListing._meta.constraints
            if constraint.name == "unique_active_favorite_listing"
        )

        assert constraint.fields == ("user", "listing")
        assert constraint.condition == models.Q(deleted_at__isnull=True)
        assert {tuple(index.fields) for index in FavoriteListing._meta.indexes} == {
            ("user", "created_at"),
            ("listing", "created_at"),
        }

    def test_active_uniqueness_is_enforced_per_user_and_listing(self):
        favorite = FavoriteListingFactory()

        with pytest.raises(IntegrityError):
            FavoriteListingFactory(user=favorite.user, listing=favorite.listing)

    def test_user_isolation_allows_the_same_listing_for_other_users(self):
        listing = _make_vacant_listing()
        first_user = TenantFactory()
        second_user = TenantFactory()

        first = FavoriteListingFactory(user=first_user, listing=listing)
        second = FavoriteListingFactory(user=second_user, listing=listing)

        assert first.listing_id == listing.id
        assert second.listing_id == listing.id

    def test_soft_deleted_favorite_can_be_recreated(self):
        favorite = FavoriteListingFactory()
        favorite.delete()

        recreated = FavoriteListingFactory(user=favorite.user, listing=favorite.listing)

        assert recreated.id != favorite.id


@pytest.mark.django_db
class TestListingSignals:
    def test_auto_create_listing_on_vacant_property(self):
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner, status=PropertyStatus.VACANT)
        listing = prop.listing
        assert listing is not None
        assert listing.is_active is True

    def test_no_listing_for_rented_property_on_create(self):
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner, status=PropertyStatus.RENTED)
        with pytest.raises(Listing.DoesNotExist):
            _ = prop.listing

    def test_auto_unpublish_when_property_rented(self):
        listing = _make_vacant_listing()
        listing.property.status = PropertyStatus.RENTED
        listing.property.save(update_fields=["status", "updated_at"])
        listing.refresh_from_db()
        assert listing.is_active is False

    def test_auto_republish_when_property_vacant(self):
        listing = _make_vacant_listing(is_active=False)
        listing.property.status = PropertyStatus.VACANT
        listing.property.save(update_fields=["status", "updated_at"])
        listing.refresh_from_db()
        assert listing.is_active is True

    def test_create_listing_if_missing_when_property_becomes_vacant(self):
        district = DistrictFactory()
        owner = OwnerFactory()
        prop = PropertyFactory(district=district, owner=owner, status=PropertyStatus.RENTED)
        assert not hasattr(prop, "listing") or Listing.objects.filter(property=prop).count() == 0
        prop.status = PropertyStatus.VACANT
        prop.save(update_fields=["status", "updated_at"])
        listing = prop.listing
        assert listing is not None
        assert listing.is_active is True

    def test_draft_listing_not_published_on_vacant(self):
        """A wizard DRAFT listing must NOT be auto-published when the property goes vacant."""
        from core.constants import ListingStatus

        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, status=PropertyStatus.PENDING_REVIEW)
        listing = Listing.objects.create(property=prop, status=ListingStatus.DRAFT, is_active=False)
        prop.status = PropertyStatus.VACANT
        prop.save(update_fields=["status", "updated_at"])
        listing.refresh_from_db()
        assert listing.status == ListingStatus.DRAFT
        assert listing.is_active is False

    def test_pending_review_listing_published_on_vacant(self):
        """An approved (PENDING_REVIEW) listing publishes exactly once — no double-create."""
        from core.constants import ListingStatus

        owner = OwnerFactory()
        prop = PropertyFactory(owner=owner, status=PropertyStatus.PENDING_REVIEW)
        listing = Listing.objects.create(property=prop, status=ListingStatus.PENDING_REVIEW, is_active=False)
        prop.status = PropertyStatus.VACANT
        prop.save(update_fields=["status", "updated_at"])
        listing.refresh_from_db()
        assert listing.status == ListingStatus.PUBLISHED
        assert listing.is_active is True
        assert listing.published_at is not None
        assert Listing.objects.filter(property=prop).count() == 1
