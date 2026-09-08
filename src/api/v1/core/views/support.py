import logging
from http import HTTPStatus

import django_q.tasks
from django.utils.translation import gettext_lazy as _
from dmr import Body

from api.v1.core.schemas.support import SupportInquiryInput, SupportInquiryOutput
from core.api.views import BaseController
from core.models import SupportInquiry
from core.utils.rate_limit import rate_limit

logger = logging.getLogger(__name__)


class SupportInquiryCreateView(BaseController):
    auth = ()

    @rate_limit(requests=5, window_seconds=3600)
    def post(self, parsed_body: Body[SupportInquiryInput]) -> dict:
        if parsed_body.website_url:
            return self.ok(
                SupportInquiryOutput(
                    status="received",
                    message=str(_("Inquiry received successfully.")),
                ).model_dump(mode="json"),
                status_code=HTTPStatus.CREATED,
            )

        ip = self.request.META.get("HTTP_X_FORWARDED_FOR")
        ip = ip.split(",")[0].strip() if ip else self.request.META.get("REMOTE_ADDR")
        user_agent = (self.request.META.get("HTTP_USER_AGENT") or "")[:512]

        inquiry = SupportInquiry.objects.create(
            name=parsed_body.name,
            email=parsed_body.email,
            message=parsed_body.message,
            ip_address=ip,
            user_agent=user_agent,
        )

        try:
            django_q.tasks.async_task("core.tasks.send_support_inquiry_telegram_alert_task", inquiry.id)
        except Exception:
            logger.warning("Unable to enqueue support inquiry telegram alert id=%s", inquiry.id, exc_info=True)

        return self.ok(
            SupportInquiryOutput(
                id=inquiry.id,
                status=inquiry.status,
                message=str(_("Inquiry received successfully.")),
            ).model_dump(mode="json"),
            status_code=HTTPStatus.CREATED,
        )
