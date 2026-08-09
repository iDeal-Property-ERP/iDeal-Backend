import factory
from notification.models import DeviceToken, Notification, NotificationPreference

from core.constants import DevicePlatform, NotificationAudience, NotificationType

from .account import UserFactory


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    recipient = factory.SubFactory(UserFactory)
    type = NotificationType.GENERAL
    audience = NotificationAudience.BOTH
    title = factory.Faker("sentence", nb_words=4)
    body = factory.Faker("text", max_nb_chars=200)
    is_read = False


class DeviceTokenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DeviceToken

    user = factory.SubFactory(UserFactory)
    token = factory.Sequence(lambda n: f"device-token-{n}")
    platform = DevicePlatform.ANDROID
    device_id = factory.Sequence(lambda n: f"device-{n}")
    app_version = "1.0.0"
    locale = "en"
    is_active = True


class NotificationPreferenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = NotificationPreference

    user = factory.SubFactory(UserFactory)
    push_enabled = True
    payments_enabled = True
    bookings_enabled = True
    maintenance_enabled = True
    leases_enabled = True
    general_enabled = True
