import json

import pytest

from tests.factories import DistrictFactory


@pytest.mark.django_db
class TestPublicListingSubmit:
    def test_submit_valid_listing(self, client):
        district = DistrictFactory(city="Toshkent")

        payload = {
            "contact": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.guest@example.com",
                "phone": "+998901234567"
            },
            "property_type": "apartment",
            "name": "Cozy Apartment in Center",
            "district_id": district.id,
            "rooms": 2,
            "area_sqm": 60,
            "floor": 3,
            "furnishing": "furnished",
            "monthly_price": 500,
            "deposit_amount": 500,
            "currency": "USD"
        }

        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        # Create a dummy image
        img_io = BytesIO()
        Image.new('RGB', (100, 100), color='red').save(img_io, 'JPEG')
        img_content = img_io.getvalue()

        files = {
            "payload": json.dumps(payload),
        }
        for i in range(5):
            files[f"images__{i}"] = SimpleUploadedFile(
                f"photo_{i}.jpg", img_content, content_type="image/jpeg"
            )

        # Manually construct multipart data because django test client doesn't
        # seamlessly support array of files with the same key "images" via dict.
        # But wait, django test client DOES support it if you provide a list or use MultiPartParser.
        # Let's just use MultiValueDict logic or pass it as a list.

        response = client.post("/api/v1/marketplace/listings/submit/", {
            "payload": json.dumps(payload),
            "images": [
                SimpleUploadedFile("photo_0.jpg", img_content, content_type="image/jpeg"),
                SimpleUploadedFile("photo_1.jpg", img_content, content_type="image/jpeg"),
                SimpleUploadedFile("photo_2.jpg", img_content, content_type="image/jpeg"),
                SimpleUploadedFile("photo_3.jpg", img_content, content_type="image/jpeg"),
                SimpleUploadedFile("photo_4.jpg", img_content, content_type="image/jpeg")
            ]
        })

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert "id" in body["data"]

        from account.models import User
        user = User.objects.get(email="john.guest@example.com")
        assert user.is_active is False
        assert user.role == "owner"

        from marketplace.models import Listing
        listing = Listing.objects.get(id=body["data"]["id"])
        assert listing.property.owner == user
        assert listing.property.photos.count() == 5
