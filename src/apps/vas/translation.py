from modeltranslation.translator import TranslationOptions, register
from vas.models import ServiceCatalogItem


@register(ServiceCatalogItem)
class ServiceCatalogItemTranslationOptions(TranslationOptions):
    fields = ("name", "description")
