from mobile_config.models import MobileHomeBanner
from modeltranslation.translator import TranslationOptions, register


@register(MobileHomeBanner)
class MobileHomeBannerTranslationOptions(TranslationOptions):
    fields = ("title", "description", "tag")
