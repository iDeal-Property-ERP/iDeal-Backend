import pytest
from mobile_config.models import MobileCriticalUpdateRange, MobileUpdatePolicy

from core.constants import DevicePlatform


@pytest.mark.integration
@pytest.mark.django_db
class TestMobileVersionConfigAPI:
    url = "/api/v1/mobile/config/version/"

    def test_missing_headers_returns_400(self, api_client):
        # Missing all custom headers
        res = api_client.get(self.url)
        assert res.status_code == 400
        data = res.json()
        assert data["success"] is False

        # Missing version
        res_no_ver = api_client.get(self.url, HTTP_X_APP_PLATFORM="android")
        assert res_no_ver.status_code == 400
        assert res_no_ver.json()["success"] is False

        # Missing platform
        res_no_plat = api_client.get(self.url, HTTP_X_APP_VERSION="1.0.0")
        assert res_no_plat.status_code == 400
        assert res_no_plat.json()["success"] is False

    def test_invalid_platform_header_returns_400(self, api_client):
        for invalid_plat in ["windows", "web", "linux", "macos", ""]:
            res = api_client.get(self.url, HTTP_X_APP_PLATFORM=invalid_plat, HTTP_X_APP_VERSION="1.0.0")
            assert res.status_code == 400
            assert res.json()["success"] is False

    def test_invalid_version_header_returns_400(self, api_client):
        for invalid_ver in ["1.0", "v1.0.0", "1.0.0-rc1", "1.0.0+1", "abc", ""]:
            res = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION=invalid_ver)
            assert res.status_code == 400
            assert res.json()["success"] is False

    def test_case_insensitive_platform_header(self, api_client):
        MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="1.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        for plat_header in ["ANDROID", "Android", "android"]:
            res = api_client.get(self.url, HTTP_X_APP_PLATFORM=plat_header, HTTP_X_APP_VERSION="1.0.0")
            assert res.status_code == 200
            assert res.json()["success"] is True

    def test_unauthenticated_public_access_and_cache_control(self, api_client):
        res = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.0.0")
        assert res.status_code == 200
        assert res.headers.get("Cache-Control") == "no-store"

    def test_no_active_policy_returns_none(self, api_client):
        # When no policy is in the DB
        res = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.0.0")
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["data"] == {
            "update_type": "none",
            "current_version": "1.0.0",
            "latest_version": None,
            "store_url": None,
        }

    def test_inactive_policy_is_ignored(self, api_client):
        MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=False,
        )
        res = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.0.0")
        assert res.status_code == 200
        body = res.json()
        assert body["data"]["update_type"] == "none"
        assert body["data"]["latest_version"] is None

    def test_current_or_newer_version_returns_none(self, api_client):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="1.5.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )

        # Equal version
        res_eq = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.5.0")
        assert res_eq.status_code == 200
        assert res_eq.json()["data"] == {
            "update_type": "none",
            "current_version": "1.5.0",
            "latest_version": "1.5.0",
            "store_url": policy.store_url,
        }

        # Newer version
        res_new = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="2.0.0")
        assert res_new.status_code == 200
        assert res_new.json()["data"] == {
            "update_type": "none",
            "current_version": "2.0.0",
            "latest_version": "1.5.0",
            "store_url": policy.store_url,
        }

    def test_older_version_without_critical_range_returns_normal(self, api_client):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        res = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.0.0")
        assert res.status_code == 200
        assert res.json()["data"] == {
            "update_type": "normal",
            "current_version": "1.0.0",
            "latest_version": "2.0.0",
            "store_url": policy.store_url,
        }

    def test_older_version_in_critical_range_returns_critical(self, api_client):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        MobileCriticalUpdateRange.objects.create(
            policy=policy,
            minimum_version="0.1.0",
            maximum_version="0.9.0",
            is_active=True,
        )

        # Inside critical range
        res = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="0.5.0")
        assert res.status_code == 200
        assert res.json()["data"] == {
            "update_type": "critical",
            "current_version": "0.5.0",
            "latest_version": "2.0.0",
            "store_url": policy.store_url,
        }

    def test_critical_range_boundaries(self, api_client):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="3.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        MobileCriticalUpdateRange.objects.create(
            policy=policy,
            minimum_version="1.0.0",
            maximum_version="1.5.0",
            is_active=True,
        )

        # Inclusive minimum boundary
        res_min = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.0.0")
        assert res_min.json()["data"]["update_type"] == "critical"

        # Inclusive maximum boundary
        res_max = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.5.0")
        assert res_max.json()["data"]["update_type"] == "critical"

        # Below minimum boundary
        res_below = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="0.9.9")
        assert res_below.json()["data"]["update_type"] == "normal"

        # Above maximum boundary (but < latest_version)
        res_above = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.5.1")
        assert res_above.json()["data"]["update_type"] == "normal"

    def test_exact_critical_range(self, api_client):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        MobileCriticalUpdateRange.objects.create(
            policy=policy,
            minimum_version="1.2.0",
            maximum_version="1.2.0",
            is_active=True,
        )

        # Exact target version -> critical
        res_exact = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.2.0")
        assert res_exact.json()["data"]["update_type"] == "critical"

        # Slightly different version -> normal
        res_other = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.1.9")
        assert res_other.json()["data"]["update_type"] == "normal"

    def test_inactive_critical_range_ignored(self, api_client):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        MobileCriticalUpdateRange.objects.create(
            policy=policy,
            minimum_version="1.0.0",
            maximum_version="1.5.0",
            is_active=False,
        )

        res = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.2.0")
        assert res.json()["data"]["update_type"] == "normal"

    def test_platform_isolation(self, api_client):
        android_policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        MobileCriticalUpdateRange.objects.create(
            policy=android_policy,
            minimum_version="1.0.0",
            maximum_version="1.5.0",
            is_active=True,
        )

        ios_policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.IOS,
            latest_version="3.0.0",
            store_url="https://apps.apple.com/app/id999999",
            is_active=True,
        )
        MobileCriticalUpdateRange.objects.create(
            policy=ios_policy,
            minimum_version="0.1.0",
            maximum_version="0.5.0",
            is_active=True,
        )

        # Android request on 1.2.0 -> critical (in android range)
        res_android = api_client.get(self.url, HTTP_X_APP_PLATFORM="android", HTTP_X_APP_VERSION="1.2.0")
        assert res_android.json()["data"]["update_type"] == "critical"
        assert res_android.json()["data"]["latest_version"] == "2.0.0"
        assert res_android.json()["data"]["store_url"] == android_policy.store_url

        # iOS request on 1.2.0 -> normal (outside ios range [0.1.0 .. 0.5.0])
        res_ios = api_client.get(self.url, HTTP_X_APP_PLATFORM="ios", HTTP_X_APP_VERSION="1.2.0")
        assert res_ios.json()["data"]["update_type"] == "normal"
        assert res_ios.json()["data"]["latest_version"] == "3.0.0"
        assert res_ios.json()["data"]["store_url"] == ios_policy.store_url
