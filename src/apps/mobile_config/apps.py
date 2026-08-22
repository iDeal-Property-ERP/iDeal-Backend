from django.apps import AppConfig


class MobileConfigConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"  # type: ignore[assignment]
    name = "mobile_config"
