# type: ignore
import factory
from mobile_config.models import MobileCriticalUpdateRange, MobileHomeBanner, MobileUpdatePolicy

from core.constants import DevicePlatform


class MobileUpdatePolicyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MobileUpdatePolicy

    platform = DevicePlatform.ANDROID
    latest_version = "1.0.0"
    store_url = "https://play.google.com/store/apps/details?id=com.ideal.mobile"
    is_active = True


class MobileCriticalUpdateRangeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MobileCriticalUpdateRange

    policy = factory.SubFactory(MobileUpdatePolicyFactory)
    minimum_version = "0.0.1"
    maximum_version = "0.9.0"
    is_active = True


class MobileHomeBannerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MobileHomeBanner

    title = "100% Actual Listings"
    description = "Whatever you see is available. No expired listings or outdated offers."
    tag = ""
    icon = "circle_check"
    sort_order = 1
    is_active = True
