import factory
from mobile_config.models import MobileCriticalUpdateRange, MobileUpdatePolicy

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
