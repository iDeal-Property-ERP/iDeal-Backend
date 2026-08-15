# pi-lens-ignore: reportMissingImports
from django.conf import settings

from api.v1.mobile.support.schemas import MobileSupportLinksOutput
from core.api.views import BaseController


class MobileSupportLinksView(BaseController):
    auth = ()

    def get(self) -> dict:
        data = MobileSupportLinksOutput(
            telegram_url=getattr(settings, "SUPPORT_TELEGRAM_URL", "") or None,
            whatsapp_url=getattr(settings, "SUPPORT_WHATSAPP_URL", "") or None,
        ).model_dump(mode="json")
        return self.ok(data)
