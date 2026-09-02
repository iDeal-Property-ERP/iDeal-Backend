"""Localized content service for managing multilingual translation maps,
validating completeness, and synchronizing translations across models.
"""

from typing import Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from core.utils.html_sanitizer import sanitize_description_html

SUPPORTED_LOCALES = ("en", "uz", "ru")
DEFAULT_LOCALE = "en"


class LocalizedContentService:
    def __init__(self, locales: tuple[str, ...] = SUPPORTED_LOCALES):
        self.locales = locales

    def apply_translations(
        self,
        instance: Any,
        translations: dict[str, dict[str, Any]],
        fields: list[str],
    ) -> None:
        """Apply a translation map `{"en": {...}, "uz": {...}, "ru": {...}}` to model instance fields."""
        if not translations:
            return

        for locale in self.locales:
            locale_data = translations.get(locale)
            if locale_data is None or not isinstance(locale_data, dict):
                continue
            for field in fields:
                if field in locale_data:
                    val = locale_data[field]
                    if field == "description" and isinstance(val, str | type(None)):
                        val = sanitize_description_html(val)
                    field_name = f"{field}_{locale}"
                    if hasattr(instance, field_name):
                        setattr(instance, field_name, val)
                    # Also set base field if locale is default
                    if locale == DEFAULT_LOCALE and hasattr(instance, field):
                        setattr(instance, field, val)

    def extract_translations(
        self,
        instance: Any,
        fields: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Extract translations from instance fields into `{"en": {...}, "uz": {...}, "ru": {...}}`."""
        result: dict[str, dict[str, Any]] = {}
        for locale in self.locales:
            locale_dict: dict[str, Any] = {}
            for field in fields:
                attr_name = f"{field}_{locale}"
                val = getattr(instance, attr_name, None)
                if val is None and locale == DEFAULT_LOCALE:
                    val = getattr(instance, field, None)
                locale_dict[field] = val
            result[locale] = locale_dict
        return result

    def validate_completeness(
        self,
        instance: Any,
        required_fields: list[str],
        optional_fields: list[str] | None = None,
    ) -> dict[str, list[str]]:
        """Validate that all required fields are present in all locales,
        and optional fields satisfy the all-or-none rule (all blank or all present).
        Returns a dict of missing fields per locale: `{"en": [...], "uz": [...], "ru": [...]}`.
        """
        missing_by_locale: dict[str, list[str]] = {loc: [] for loc in self.locales}

        # Check required fields
        for field in required_fields:
            for locale in self.locales:
                val = getattr(instance, f"{field}_{locale}", None)
                if val is None or (isinstance(val, str) and not val.strip()):
                    missing_by_locale[locale].append(field)

        # Check optional fields (all-or-none)
        if optional_fields:
            for field in optional_fields:
                filled_locales = []
                empty_locales = []
                for locale in self.locales:
                    val = getattr(instance, f"{field}_{locale}", None)
                    if val is not None and isinstance(val, str) and val.strip():
                        filled_locales.append(locale)
                    else:
                        empty_locales.append(locale)

                if filled_locales and empty_locales:
                    # Partial translation violates all-or-none
                    for locale in empty_locales:
                        missing_by_locale[locale].append(field)

        return missing_by_locale

    def enforce_publication_completeness(
        self,
        property_instance: Any,
    ) -> None:
        """Enforce that a property, its active linked district, and its active linked amenities
        are completely translated before publication.
        """
        # Property required fields: name
        # Property optional fields: description
        prop_missing = self.validate_completeness(
            property_instance,
            required_fields=["name"],
            optional_fields=["description"],
        )
        has_prop_missing = any(len(fields) > 0 for fields in prop_missing.values())
        if has_prop_missing:
            raise ValidationError(_("Property translation is incomplete across supported languages (EN, UZ, RU)."))

        # Linked District completeness
        if property_instance.district_id:
            district_missing = self.validate_completeness(
                property_instance.district,
                required_fields=["name", "city"],
            )
            if any(len(fields) > 0 for fields in district_missing.values()):
                raise ValidationError(
                    _("Linked district '%(district)s' has incomplete translations.")
                    % {"district": str(property_instance.district.name)}
                )

        # Linked Amenities completeness
        for amenity in property_instance.amenities.filter(is_active=True):
            amenity_missing = self.validate_completeness(
                amenity,
                required_fields=["name"],
            )
            if any(len(fields) > 0 for fields in amenity_missing.values()):
                raise ValidationError(
                    _("Linked amenity '%(amenity)s' has incomplete translations.") % {"amenity": str(amenity.name)}
                )

    def sync_property_listing_translations(
        self,
        property_instance: Any,
        listing_instance: Any = None,
    ) -> None:
        """Explicitly copy property description translation columns to listing."""
        if listing_instance is None:
            try:
                listing_instance = property_instance.listing
            except Exception:
                return

        if listing_instance is None:
            return

        update_fields = []
        for locale in self.locales:
            prop_val = getattr(property_instance, f"description_{locale}", None)
            list_val = getattr(listing_instance, f"description_{locale}", None)
            if list_val != prop_val:
                setattr(listing_instance, f"description_{locale}", prop_val)
                update_fields.append(f"description_{locale}")

        if listing_instance.description != property_instance.description:
            listing_instance.description = property_instance.description
            update_fields.append("description")

        if update_fields:
            update_fields.append("updated_at")
            listing_instance.save(update_fields=update_fields)

    def get_localization_status(self) -> dict[str, Any]:
        """Aggregate localization completeness status across all translatable resources."""
        from contract.models import PublicOffer
        from marketplace.models import FaqItem
        from property.models import Amenity, District, Property
        from vas.models import ServiceCatalogItem

        resources = {
            "properties": {
                "qs": Property.objects.all(),
                "required": ["name"],
                "optional": ["description"],
                "name_attr": "name",
            },
            "districts": {
                "qs": District.objects.all(),
                "required": ["name", "city"],
                "optional": [],
                "name_attr": "name",
            },
            "amenities": {
                "qs": Amenity.objects.filter(is_active=True),
                "required": ["name"],
                "optional": [],
                "name_attr": "name",
            },
            "faqs": {
                "qs": FaqItem.objects.filter(is_active=True),
                "required": ["question", "answer"],
                "optional": [],
                "name_attr": "question",
            },
            "public_offers": {
                "qs": PublicOffer.objects.filter(is_active=True),
                "required": ["body"],
                "optional": [],
                "name_attr": "version",
            },
            "vas_catalog_items": {
                "qs": ServiceCatalogItem.objects.filter(is_active=True),
                "required": ["name"],
                "optional": ["description"],
                "name_attr": "name",
            },
        }

        status_report: dict[str, Any] = {}

        for resource_name, config in resources.items():
            qs = config["qs"]
            required = config["required"]
            optional = config["optional"]
            name_attr = config["name_attr"]

            total_count = qs.count()
            incomplete_items = []
            missing_counts_by_lang = {loc: 0 for loc in self.locales}

            for item in qs.iterator():
                missing = self.validate_completeness(item, required, optional)
                is_item_incomplete = False
                for loc, fields in missing.items():
                    if fields:
                        missing_counts_by_lang[loc] += 1
                        is_item_incomplete = True

                if is_item_incomplete:
                    incomplete_items.append(
                        {
                            "id": item.id,
                            "identifier": str(getattr(item, name_attr, f"#{item.id}")),
                            "missing_by_language": {loc: f for loc, f in missing.items() if f},
                        }
                    )

            status_report[resource_name] = {
                "total_count": total_count,
                "complete_count": total_count - len(incomplete_items),
                "incomplete_count": len(incomplete_items),
                "missing_by_language": missing_counts_by_lang,
                "incomplete_items": incomplete_items[:50],
            }

        return status_report
