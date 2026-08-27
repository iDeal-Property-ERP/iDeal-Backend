from marketplace.models import FaqItem, Listing
from modeltranslation.translator import TranslationOptions, register


@register(Listing)
class ListingTranslationOptions(TranslationOptions):
    fields = ("description",)


@register(FaqItem)
class FaqItemTranslationOptions(TranslationOptions):
    fields = ("question", "answer")
