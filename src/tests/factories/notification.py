import factory
from notification.models import Notification

from core.constants import NotificationType

from .account import UserFactory


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    recipient = factory.SubFactory(UserFactory)
    type = NotificationType.GENERAL
    title = factory.Faker("sentence", nb_words=4)
    body = factory.Faker("text", max_nb_chars=200)
    is_read = False
