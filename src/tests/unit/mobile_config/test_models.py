import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from mobile_config.models import MobileCriticalUpdateRange, MobileUpdatePolicy

from core.constants import DevicePlatform


@pytest.mark.unit
@pytest.mark.django_db
class TestMobileConfigModels:
    def test_policy_clean_valid(self):
        policy = MobileUpdatePolicy(
            platform=DevicePlatform.ANDROID,
            latest_version="1.2.3",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        policy.clean()  # Should not raise

    def test_policy_clean_invalid_semver(self):
        policy = MobileUpdatePolicy(
            platform=DevicePlatform.ANDROID,
            latest_version="v1.2.3",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        with pytest.raises(ValidationError) as exc_info:
            policy.clean()
        assert "latest_version" in exc_info.value.message_dict

    def test_policy_clean_non_https_store_url(self):
        policy = MobileUpdatePolicy(
            platform=DevicePlatform.IOS,
            latest_version="1.0.0",
            store_url="http://apps.apple.com/app/id123456",
            is_active=True,
        )
        with pytest.raises(ValidationError) as exc_info:
            policy.clean()
        assert "store_url" in exc_info.value.message_dict

    def test_critical_range_clean_valid(self):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        cr_range = MobileCriticalUpdateRange(
            policy=policy,
            minimum_version="0.1.0",
            maximum_version="0.9.0",
            is_active=True,
        )
        cr_range.clean()

    def test_critical_range_clean_exact_version(self):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        cr_range = MobileCriticalUpdateRange(
            policy=policy,
            minimum_version="0.5.0",
            maximum_version="0.5.0",
            is_active=True,
        )
        cr_range.clean()

    def test_critical_range_clean_invalid_order(self):
        policy = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        cr_range = MobileCriticalUpdateRange(
            policy=policy,
            minimum_version="1.0.0",
            maximum_version="0.9.0",
            is_active=True,
        )
        with pytest.raises(ValidationError) as exc_info:
            cr_range.clean()
        assert "maximum_version" in exc_info.value.message_dict

    def test_unique_active_policy_per_platform(self):
        MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="1.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=True,
        )
        with pytest.raises(IntegrityError):
            MobileUpdatePolicy.objects.create(
                platform=DevicePlatform.ANDROID,
                latest_version="2.0.0",
                store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
                is_active=True,
            )

    def test_multiple_inactive_policies_allowed(self):
        p1 = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="1.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=False,
        )
        p2 = MobileUpdatePolicy.objects.create(
            platform=DevicePlatform.ANDROID,
            latest_version="2.0.0",
            store_url="https://play.google.com/store/apps/details?id=com.ideal.mobile",
            is_active=False,
        )
        assert p1.id is not None
        assert p2.id is not None
