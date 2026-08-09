from http import HTTPStatus

from django.utils import timezone
from dmr import Path, Query
from notification.models import Notification

from api.v1.mobile.notifications.schemas import (
    MobileNotificationFilterQuery,
    MobileNotificationOutput,
    UnreadCountOutput,
)
from core.api.views import BaseController, DetailPath, GenericController
from core.constants import NOTIFICATION_TYPE_CATEGORY, NotificationAudience
from core.utils.pagination import build_paginated_response_from_queryset


class MobileNotificationQueryMixin:
    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user,
            audience__in=(NotificationAudience.MOBILE, NotificationAudience.BOTH),
        )


class MobileNotificationListView(MobileNotificationQueryMixin, GenericController):
    model = Notification
    output_schema = MobileNotificationOutput

    def get(self, parsed_query: Query[MobileNotificationFilterQuery]) -> dict:
        queryset = self.get_queryset()
        if parsed_query.is_read is not None:
            queryset = queryset.filter(is_read=parsed_query.is_read)
        if parsed_query.category is not None:
            notification_types = [
                notification_type
                for notification_type, category in NOTIFICATION_TYPE_CATEGORY.items()
                if category == parsed_query.category
            ]
            queryset = queryset.filter(type__in=notification_types)

        paginated = build_paginated_response_from_queryset(
            queryset,
            parsed_query.page,
            parsed_query.per_page,
            self.to_output,
        )
        return self.ok(paginated)


class MobileNotificationUnreadCountView(MobileNotificationQueryMixin, BaseController):
    def get(self) -> dict:
        count = self.get_queryset().filter(is_read=False).count()
        return self.ok(UnreadCountOutput(unread_count=count).model_dump(mode="json"))


class MobileNotificationReadView(MobileNotificationQueryMixin, GenericController):
    model = Notification
    output_schema = MobileNotificationOutput

    def post(self, parsed_path: Path[DetailPath]) -> dict:
        notification = self.get_object(pk=parsed_path.pk)
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at", "updated_at"])
        return self.ok(self.to_output(notification), status_code=HTTPStatus.OK)


class MobileNotificationReadAllView(MobileNotificationQueryMixin, BaseController):
    def post(self) -> dict:
        updated = self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return self.ok({"updated": updated}, status_code=HTTPStatus.OK)
