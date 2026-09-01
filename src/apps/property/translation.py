from modeltranslation.translator import TranslationOptions, register
from property.models import Amenity, District, Property, PropertyPhoto


@register(District)
class DistrictTranslationOptions(TranslationOptions):
    fields = ("name", "city")


@register(Amenity)
class AmenityTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Property)
class PropertyTranslationOptions(TranslationOptions):
    fields = ("name", "description", "landmark")


@register(PropertyPhoto)
class PropertyPhotoTranslationOptions(TranslationOptions):
    fields = ("caption",)
