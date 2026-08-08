import requests
from account.services.auth.providers.base import OTPDeliveryError, OTPMessage, OTPProvider
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

ESKIZ_TOKEN_TTL = 60 * 60 * 24 * 25
ESKIZ_TOKEN_CACHE_KEY = "otp:eskiz:token"


class EskizGateway(OTPProvider):
    provider_name = "eskiz"

    def __init__(self, *, cache_backend=cache, http_client=requests):
        super().__init__(http_client=http_client)
        self.cache = cache_backend

    def _token(self, *, force_refresh: bool = False) -> str:
        if not force_refresh:
            cached_token = self.cache.get(ESKIZ_TOKEN_CACHE_KEY)
            if cached_token:
                return cached_token

        email = settings.ESKIZ_EMAIL
        password = settings.ESKIZ_PASSWORD
        if not email or not password:
            raise OTPDeliveryError("Eskiz credentials are not configured")

        base_url = settings.ESKIZ_BASE_URL.rstrip("/")
        response = self._post(
            f"{base_url}/auth/login",
            data={"email": email, "password": password},
        )
        payload = self._json_payload(response)
        if response.status_code >= 400:
            raise self._provider_error(response)

        data = payload.get("data")
        token = data.get("token") if isinstance(data, dict) else None
        token = token or payload.get("token")
        if not isinstance(token, str) or not token:
            raise self._provider_error(response)

        self.cache.set(ESKIZ_TOKEN_CACHE_KEY, token, timeout=ESKIZ_TOKEN_TTL)
        return token

    def _send_message(self, token: str, message: OTPMessage):
        base_url = settings.ESKIZ_BASE_URL.rstrip("/")
        text = str(_("iDeal tasdiqlash kodi: %(code)s")) % {"code": message.code}
        return self._post(
            f"{base_url}/message/sms/send",
            headers={"Authorization": f"Bearer {token}"},
            data={"mobile_phone": message.phone, "message": text, "from": settings.ESKIZ_FROM},
        )

    def send(self, message: OTPMessage) -> None:
        token = self._token()
        response = self._send_message(token, message)
        if response.status_code == 401:
            self.cache.delete(ESKIZ_TOKEN_CACHE_KEY)
            token = self._token(force_refresh=True)
            response = self._send_message(token, message)

        payload = self._json_payload(response)
        if response.status_code >= 400 or self._payload_indicates_error(payload):
            raise self._provider_error(response)
