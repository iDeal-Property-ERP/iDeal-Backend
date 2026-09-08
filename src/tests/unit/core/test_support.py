import json
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.urls import reverse

from core.constants import SupportInquiryStatus
from core.models import SupportInquiry
from core.services.support import send_support_inquiry_telegram_alert


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


def _post(api_client, path, payload):
    return api_client.post(path, data=json.dumps(payload), content_type="application/json")


@pytest.mark.unit
@pytest.mark.django_db
class TestSupportInquiryAPI:
    @patch("django_q.tasks.async_task")
    def test_create_inquiry_success(self, mock_async_task, api_client):
        url = reverse("url_router:v1:support:inquiry-create")
        payload = {
            "name": "Alex Smith",
            "email": "alex@example.com",
            "message": "I need help with my account login.",
        }
        response = _post(api_client, url, payload)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == SupportInquiryStatus.NEW
        assert data["data"]["id"] is not None

        inquiry = SupportInquiry.objects.get(pk=data["data"]["id"])
        assert inquiry.name == "Alex Smith"
        assert inquiry.email == "alex@example.com"
        assert inquiry.message == "I need help with my account login."
        assert inquiry.status == SupportInquiryStatus.NEW
        mock_async_task.assert_called_once_with("core.tasks.send_support_inquiry_telegram_alert_task", inquiry.id)

    @patch("django_q.tasks.async_task")
    def test_honeypot_drops_silently(self, mock_async_task, api_client):
        url = reverse("url_router:v1:support:inquiry-create")
        payload = {
            "name": "Bot Spammer",
            "email": "spam@bot.com",
            "message": "Buy cheap stuff immediately!",
            "website_url": "https://spam-bot.com",
        }
        response = _post(api_client, url, payload)
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["id"] is None
        assert SupportInquiry.objects.count() == 0
        mock_async_task.assert_not_called()

    def test_invalid_email_fails(self, api_client):
        url = reverse("url_router:v1:support:inquiry-create")
        payload = {
            "name": "Alex Smith",
            "email": "not-an-email",
            "message": "Valid message with more than ten characters.",
        }
        response = _post(api_client, url, payload)
        assert response.status_code == 400

    def test_short_message_fails(self, api_client):
        url = reverse("url_router:v1:support:inquiry-create")
        payload = {
            "name": "Alex Smith",
            "email": "alex@example.com",
            "message": "Too short",
        }
        response = _post(api_client, url, payload)
        assert response.status_code == 400


@pytest.mark.unit
@pytest.mark.django_db
class TestSupportInquiryTelegramAlert:
    @patch("requests.post")
    def test_send_alert_success(self, mock_post, settings):
        settings.LOGGING_TELEGRAM_BOT_TOKEN = "test-bot-token"
        settings.LOGGING_TELEGRAM_CHAT_ID = "123456789"

        inquiry = SupportInquiry.objects.create(
            name="Jane Doe",
            email="jane@example.com",
            message="Question about contract duration.",
            ip_address="127.0.0.1",
        )

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_post.return_value = mock_resp

        result = send_support_inquiry_telegram_alert(inquiry.id)
        assert result is True
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert "https://api.telegram.org/bottest-bot-token/sendMessage" in mock_post.call_args.args[0]
        assert call_kwargs["json"]["chat_id"] == "123456789"
        assert "Jane Doe" in call_kwargs["json"]["text"]
        assert "jane@example.com" in call_kwargs["json"]["text"]

    def test_send_alert_missing_credentials(self, settings):
        settings.LOGGING_TELEGRAM_BOT_TOKEN = ""
        settings.LOGGING_TELEGRAM_CHAT_ID = ""
        result = send_support_inquiry_telegram_alert(999)
        assert result is False

    def test_send_alert_nonexistent_inquiry(self, settings):
        settings.LOGGING_TELEGRAM_BOT_TOKEN = "token"
        settings.LOGGING_TELEGRAM_CHAT_ID = "chat"
        result = send_support_inquiry_telegram_alert(999999)
        assert result is False
