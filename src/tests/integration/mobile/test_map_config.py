import pytest
from django.test import override_settings

from core.utils.map_obfuscator import deobfuscate_map_token


@pytest.mark.django_db
class TestMobileMapConfigAPI:
    url = "/api/v1/mobile/config/map/"
    secret = "iDeal-Secret-Map-Seed-2025"

    def test_map_config_returns_yandex_by_default(self, api_client):
        test_key = "test-yandex-mapkit-api-key-12345"
        with override_settings(
            MAP_DEFAULT_PROVIDER="yandex",
            YANDEX_MAPKIT_API_KEY=test_key,
            MAP_OBFUSCATION_SECRET=self.secret,
        ):
            response = api_client.get(self.url)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["provider"] == "yandex"
        assert body["data"]["token"] != test_key
        assert deobfuscate_map_token(body["data"]["token"], self.secret) == test_key

    def test_map_config_returns_google_when_configured(self, api_client):
        test_key = "dummy-test-google-key-67890"
        with override_settings(
            MAP_DEFAULT_PROVIDER="google",
            GOOGLE_MAPS_API_KEY=test_key,
            MAP_OBFUSCATION_SECRET=self.secret,
        ):
            response = api_client.get(self.url)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["provider"] == "google"
        assert body["data"]["token"] != test_key
        assert deobfuscate_map_token(body["data"]["token"], self.secret) == test_key

    def test_map_config_empty_token_when_unconfigured(self, api_client):
        with override_settings(
            MAP_DEFAULT_PROVIDER="yandex",
            YANDEX_MAPKIT_API_KEY="",
        ):
            response = api_client.get(self.url)

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["provider"] == "yandex"
        assert body["data"]["token"] == ""

    def test_map_config_accessible_without_auth(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == 200
