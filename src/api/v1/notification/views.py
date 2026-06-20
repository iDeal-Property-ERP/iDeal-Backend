from http import HTTPStatus

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dmr import Path, Query
from dmr.pagination import Paginated
from notification.models import Notification

from api.v1.notification.schemas import (
    NotificationFilterQuery,
    NotificationOutput,
    UnreadCountOutput,
)
from core.api.views import BaseController, DetailPath, GenericController


class NotificationListView(GenericController):
    model = Notification
    output_schema = NotificationOutput

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def get(
        self, parsed_query: Query[NotificationFilterQuery]
    ) -> list[NotificationOutput] | Paginated[NotificationOutput]:
        qs = self.get_queryset()
        if parsed_query.is_read is not None:
            qs = qs.filter(is_read=parsed_query.is_read)
        return self.list_response(qs, parsed_query)


class NotificationUnreadCountView(BaseController):
    def get(self) -> UnreadCountOutput:
        count = Notification.objects.filter(recipient=self.request.user, is_read=False).count()
        return self.ok(UnreadCountOutput(unread_count=count).model_dump(mode="json"))


class NotificationReadView(GenericController):
    model = Notification
    output_schema = NotificationOutput

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def post(self, parsed_path: Path[DetailPath]) -> NotificationOutput:
        notification = self.get_object(pk=parsed_path.pk)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at", "updated_at"])
        return self.ok(self.to_output(notification), status_code=HTTPStatus.OK)


class NotificationReadAllView(BaseController):
    def post(self) -> dict:
        updated = Notification.objects.filter(recipient=self.request.user, is_read=False).update(
            is_read=True, read_at=timezone.now()
        )
        return self.ok(
            {"updated": updated, "message": str(_("All notifications marked as read"))},
            status_code=HTTPStatus.OK,
        )
