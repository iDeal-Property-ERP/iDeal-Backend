import pytest
from django.test import override_settings


@pytest.mark.django_db
class TestMobileSupportLinksAPI:
    url = "/api/v1/mobile/support/links/"

    def test_support_links_default_null_when_unconfigured(self, api_client):
        with override_settings(SUPPORT_TELEGRAM_URL="", SUPPORT_WHATSAPP_URL=""):
            response = api_client.get(self.url)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == {
            "telegram_url": None,
            "whatsapp_url": None,
        }

    def test_support_links_return_configured_urls(self, api_client):
        with override_settings(
            SUPPORT_TELEGRAM_URL="https://t.me/ideal_support",
            SUPPORT_WHATSAPP_URL="https://wa.me/998901234567",
        ):
            response = api_client.get(self.url)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == {
            "telegram_url": "https://t.me/ideal_support",
            "whatsapp_url": "https://wa.me/998901234567",
        }

    def test_support_links_accessible_without_auth(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == 200
