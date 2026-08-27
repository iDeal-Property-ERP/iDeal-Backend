import pytest
from django.core.exceptions import ValidationError

from core.services.localization import LocalizedContentService
from tests.factories import DistrictFactory, PropertyFactory


@pytest.mark.django_db
class TestLocalizedContentService:
    def test_apply_and_extract_translations(self):
        service = LocalizedContentService()
        district = DistrictFactory(name="Yunusobod", city="Toshkent")

        translations = {
            "en": {"name": "Yunusabad", "city": "Tashkent"},
            "uz": {"name": "Yunusobod", "city": "Toshkent"},
            "ru": {"name": "Юнусабад", "city": "Ташкент"},
        }
        service.apply_translations(district, translations, ["name", "city"])
        district.save()

        district.refresh_from_db()
        assert district.name_en == "Yunusabad"
        assert district.name_uz == "Yunusobod"
        assert district.name_ru == "Юнусабад"
        assert district.city_en == "Tashkent"
        assert district.city_uz == "Toshkent"
        assert district.city_ru == "Ташкент"

        extracted = service.extract_translations(district, ["name", "city"])
        assert extracted["en"]["name"] == "Yunusabad"
        assert extracted["uz"]["name"] == "Yunusobod"
        assert extracted["ru"]["name"] == "Юнусабад"

    def test_validate_completeness_required_and_optional(self):
        service = LocalizedContentService()
        district = DistrictFactory.build(
            name_en="Yunusabad",
            name_uz="Yunusobod",
            name_ru="",
            city_en="Tashkent",
            city_uz="Toshkent",
            city_ru="Ташкент",
        )

        missing = service.validate_completeness(district, required_fields=["name", "city"])
        assert missing["en"] == []
        assert missing["uz"] == []
        assert missing["ru"] == ["name"]

    def test_enforce_publication_completeness_fails_on_incomplete(self):
        service = LocalizedContentService()
        district = DistrictFactory(name_en="Yunusabad", name_uz="Yunusobod", name_ru="")
        prop = PropertyFactory(district=district, name_en="Villa", name_uz="Villa", name_ru="Вилла")

        with pytest.raises(ValidationError):
            service.enforce_publication_completeness(prop)

    def test_get_localization_status(self):
        service = LocalizedContentService()
        DistrictFactory(
            name_en="Chilonzor",
            name_uz="Chilonzor",
            name_ru="Чиланзар",
            city_en="Tashkent",
            city_uz="Toshkent",
            city_ru="Ташкент",
        )
        status_report = service.get_localization_status()
        assert "properties" in status_report
        assert "districts" in status_report
        assert "amenities" in status_report
        assert "faqs" in status_report
        assert "public_offers" in status_report
        assert "vas_catalog_items" in status_report
        assert status_report["districts"]["total_count"] >= 1
