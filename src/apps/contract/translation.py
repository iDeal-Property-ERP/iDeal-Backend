from contract.models import PublicOffer
from modeltranslation.translator import TranslationOptions, register


@register(PublicOffer)
class PublicOfferTranslationOptions(TranslationOptions):
    fields = ("body",)
