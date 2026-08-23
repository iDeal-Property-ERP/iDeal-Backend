import pytest

from core.constants import ListingStatus, PropertyStatus
from tests.factories import ListingFactory, OwnerFactory, PropertyFactory, PropertyPhotoFactory
from tests.integration.property.test_api import _make_jwt

pytestmark = pytest.mark.django_db

MY_LISTINGS_URL = "/api/v1/mobile/my-listings/"


def test_my_listings_returns_all_cover_image_tiers(api_client):
    owner = OwnerFactory()
    property_obj = PropertyFactory(owner=owner, status=PropertyStatus.VACANT)
    ListingFactory(property=property_obj, status=ListingStatus.PUBLISHED)
    PropertyPhotoFactory(
        property=property_obj,
        image="properties/photos/original.jpg",
        preview_image="properties/photos/preview.webp",
        display_image="properties/photos/display.webp",
        is_primary=True,
    )

    response = api_client.get(MY_LISTINGS_URL, **_make_jwt(owner))

    assert response.status_code == 200
    item = response.json()["data"]["listings"][0]
    assert item["cover_image_url"].endswith("/media/properties/photos/original.jpg")
    assert item["cover_preview_url"].endswith("/media/properties/photos/preview.webp")
    assert item["cover_display_url"].endswith("/media/properties/photos/display.webp")
