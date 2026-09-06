from django.db import migrations

DEFAULT_BANNERS = [
    {
        "icon": "circle_check",
        "sort_order": 1,
        "is_active": True,
        "title_en": "100% Actual Listings",
        "title_ru": "Только актуальные объявления",
        "title_uz": "Faqat dolzarb e'lonlar",
        "description_en": "Whatever you see is available. No expired listings or outdated offers.",
        "description_ru": "Всё, что вы видите — доступно. Никаких устаревших предложений.",
        "description_uz": "Ko'rib turgan barcha takliflar mavjud. Muddati o'tgan e'lonlar yo'q.",
    },
    {
        "icon": "shield_check",
        "sort_order": 2,
        "is_active": True,
        "title_en": "Verified Properties",
        "title_ru": "Проверенная недвижимость",
        "title_uz": "Tekshirilgan mulklar",
        "description_en": "Our team inspects each home to ensure photos and terms match reality.",
        "description_ru": "Наша команда проверяет каждое жильё и согласие собственника.",
        "description_uz": "Mutaxassislarimiz har bir uyni ko'zdan kechirib, haqiqiyligini tasdiqlaydi.",
    },
    {
        "icon": "calendar_event",
        "sort_order": 3,
        "is_active": True,
        "title_en": "We Arrange Viewings",
        "title_ru": "Организуем просмотр",
        "title_uz": "Ko'rishni tashkil qilamiz",
        "description_en": "Visit the property beforehand with our representative to assist you.",
        "description_ru": "Посетите объект заранее — наш представитель встретит вас и ответит на все вопросы.",
        "description_uz": "Uyni oldindan borib ko'ring, vakilimiz sizga hamrohlik qiladi va yordam beradi.",
    },
    {
        "icon": "file_certificate",
        "sort_order": 4,
        "is_active": True,
        "title_en": "Official Legal Agreements",
        "title_ru": "Официальные договоры",
        "title_uz": "Rasmiy shartnomalar",
        "description_en": "Every booking and purchase is protected by contracts recognized by official registries.",
        "description_ru": "Каждая сделка защищена договором, признаваемым госреестрами.",
        "description_uz": ("Har bir ijara va xarid davlat ro'yxatidan o'tuvchi rasmiy shartnoma bilan himoyalangan."),
    },
]


def seed_banners(apps, schema_editor):
    MobileHomeBanner = apps.get_model("mobile_config", "MobileHomeBanner")
    for banner_data in DEFAULT_BANNERS:
        MobileHomeBanner.objects.create(
            title=banner_data["title_en"],
            title_en=banner_data["title_en"],
            title_ru=banner_data["title_ru"],
            title_uz=banner_data["title_uz"],
            description=banner_data["description_en"],
            description_en=banner_data["description_en"],
            description_ru=banner_data["description_ru"],
            description_uz=banner_data["description_uz"],
            tag="",
            tag_en=None,
            tag_ru=None,
            tag_uz=None,
            icon=banner_data["icon"],
            sort_order=banner_data["sort_order"],
            is_active=banner_data["is_active"],
        )


def reverse_seed_banners(apps, schema_editor):
    MobileHomeBanner = apps.get_model("mobile_config", "MobileHomeBanner")
    icons = [b["icon"] for b in DEFAULT_BANNERS]
    MobileHomeBanner.objects.filter(icon__in=icons).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("mobile_config", "0002_mobilehomebanner"),
    ]

    operations = [
        migrations.RunPython(seed_banners, reverse_seed_banners),
    ]
