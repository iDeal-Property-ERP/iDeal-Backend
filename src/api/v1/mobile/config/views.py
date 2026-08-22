from django.conf import settings

from api.v1.mobile.config.schemas import MobileMapConfigOutput
from core.api.views import BaseController
from core.utils.map_obfuscator import obfuscate_map_token


class MobileMapConfigView(BaseController):
    auth = ()

    def get(self) -> dict:
        provider = getattr(settings, "MAP_DEFAULT_PROVIDER", "yandex").lower()
        if provider == "google":
            token = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
        else:
            provider = "yandex"
            token = getattr(settings, "YANDEX_MAPKIT_API_KEY", "")

        secret = getattr(settings, "MAP_OBFUSCATION_SECRET", "")
        obfuscated_token = obfuscate_map_token(token, secret) if token and secret else ""

        data = MobileMapConfigOutput(
            provider=provider,  # type: ignore[arg-type]
            token=obfuscated_token,
        ).model_dump(mode="json")
        return self.ok(data)
