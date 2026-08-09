from django.db import transaction
from django.utils import timezone
from dmr import Body
from notification.models import DeviceToken

from api.v1.mobile.devices.schemas import DeviceOutput, DeviceRegistrationInput, DeviceUnregisterInput
from core.api.views import BaseController


class DeviceRegistrationView(BaseController):
    def post(self, parsed_body: Body[DeviceRegistrationInput]) -> dict:
        payload = parsed_body.model_dump()
        token = payload.pop("token")
        device, created = DeviceToken.objects.update_or_create(
            token=token,
            defaults={
                "user": self.request.user,
                "is_active": True,
                "last_seen_at": timezone.now(),
                **payload,
            },
        )
        if not created:
            device.refresh_from_db()
        return self.ok(DeviceOutput.model_validate(device).model_dump(mode="json"))


class DeviceUnregisterView(BaseController):
    def post(self, parsed_body: Body[DeviceUnregisterInput]) -> dict:
        devices = list(DeviceToken.objects.filter(user=self.request.user, token=parsed_body.token))
        with transaction.atomic():
            for device in devices:
                device.hard_delete()
        return self.ok({"deleted": len(devices)})
