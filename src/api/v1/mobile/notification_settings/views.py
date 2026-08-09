from django.db import transaction
from dmr import Body
from notification.models import DeviceToken, NotificationPreference

from api.v1.mobile.notification_settings.schemas import NotificationSettingsOutput, NotificationSettingsUpdateInput
from core.api.views import BaseController


def _output(preference: NotificationPreference) -> dict:
    return NotificationSettingsOutput.model_validate(preference).model_dump(mode="json")


class NotificationSettingsView(BaseController):
    def get(self) -> dict:
        preference, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return self.ok(_output(preference))

    def patch(self, parsed_body: Body[NotificationSettingsUpdateInput]) -> dict:
        updates = parsed_body.model_dump(exclude_unset=True)
        with transaction.atomic():
            preference, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
            for field, value in updates.items():
                setattr(preference, field, value)
            if updates:
                preference.save(update_fields=[*updates, "updated_at"])
            if updates.get("push_enabled") is False:
                for device in DeviceToken.objects.filter(user=self.request.user):
                    device.hard_delete()
        return self.ok(_output(preference))
