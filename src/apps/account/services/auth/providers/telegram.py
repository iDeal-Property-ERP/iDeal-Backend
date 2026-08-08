from account.services.auth.providers.base import OTPDeliveryError, OTPMessage, OTPProvider
from django.conf import settings


class TelegramGateway(OTPProvider):
    provider_name = "telegram"

    def send(self, message: OTPMessage) -> None:
        token = settings.TELEGRAM_GATEWAY_TOKEN
        if not token:
            raise OTPDeliveryError("Telegram gateway token is not configured")

        response = self._post(
            "https://gatewayapi.telegram.org/sendVerificationMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"phone_number": message.phone, "code": message.code},
        )
        payload = self._json_payload(response)
        if response.status_code >= 400 or payload.get("ok") is not True:
            raise self._provider_error(response)
