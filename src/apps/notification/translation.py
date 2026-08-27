from modeltranslation.translator import TranslationOptions, register
from notification.models import Notification


@register(Notification)
class NotificationTranslationOptions(TranslationOptions):
    fields = ("title", "body")
