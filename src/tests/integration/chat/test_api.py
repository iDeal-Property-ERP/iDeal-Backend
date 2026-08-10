import json
from unittest.mock import patch

import pytest
from chat.models import Conversation, Message
from chat.services import send_message, set_archived
from django.utils import timezone

from core.constants import ChatReportReason, ChatSenderSide
from tests.factories import (
    ConversationFactory,
    ConversationReportFactory,
    MessageFactory,
    TenantFactory,
)
from tests.integration.property.test_api import _make_jwt


def _conversation_url(conversation):
    return f"/api/v1/chat/conversations/{conversation.id}/"


def _message_url(conversation):
    return f"{_conversation_url(conversation)}messages/"


def _items(response):
    return response.json()["data"]["page"]["object_list"]


@pytest.mark.django_db
def test_chat_requires_management_role_and_authentication(api_client):
    conversation = ConversationFactory()
    report = ConversationReportFactory(conversation=conversation)
    routes = [
        ("get", "/api/v1/chat/conversations/"),
        ("get", _conversation_url(conversation)),
        ("get", _message_url(conversation)),
        ("post", _message_url(conversation)),
        ("post", f"{_conversation_url(conversation)}messages/image/"),
        ("post", f"{_conversation_url(conversation)}read/"),
        ("post", f"{_conversation_url(conversation)}archive/"),
        ("post", f"{_conversation_url(conversation)}unarchive/"),
        ("post", f"{_conversation_url(conversation)}block/"),
        ("post", f"{_conversation_url(conversation)}unblock/"),
        ("delete", _conversation_url(conversation)),
        ("get", "/api/v1/chat/reports/"),
        ("post", f"/api/v1/chat/reports/{report.id}/resolve/"),
    ]
    tenant = TenantFactory()

    for method, path in routes:
        kwargs = _make_jwt(tenant)
        if method == "post" and path.endswith("messages/"):
            response = api_client.post(
                path,
                json.dumps({"text": "reply"}),
                content_type="application/json",
                **kwargs,
            )
        else:
            response = getattr(api_client, method)(path, **kwargs)
        assert response.status_code == 403, (method, path, response.content)

    for method, path in routes:
        response = getattr(api_client, method)(path)
        assert response.status_code == 401, (method, path, response.content)


@pytest.mark.django_db
def test_management_lists_conversations_with_status_filters(api_client, management):
    open_conversation = ConversationFactory()
    archived_conversation = ConversationFactory()
    reported_conversation = ConversationFactory()
    deleted_conversation = ConversationFactory()

    set_archived(archived_conversation, side=ChatSenderSide.STAFF, value=True)
    ConversationReportFactory(
        conversation=reported_conversation,
        reason=ChatReportReason.SPAM,
        resolved_at=None,
    )
    deleted_conversation.user_deleted_at = timezone.now()
    deleted_conversation.save(update_fields=["user_deleted_at", "updated_at"])

    expected = {
        "open": {open_conversation.id, reported_conversation.id, deleted_conversation.id},
        "archived": {archived_conversation.id},
        "reported": {reported_conversation.id},
        "deleted_by_user": {deleted_conversation.id},
    }
    for status, expected_ids in expected.items():
        response = api_client.get(
            f"/api/v1/chat/conversations/?status={status}&per_page=100",
            **_make_jwt(management),
        )
        assert response.status_code == 200
        assert {item["id"] for item in _items(response)} == expected_ids


@pytest.mark.django_db
def test_management_searches_conversations_by_listing_title_and_user_phone(api_client, management):
    title_conversation = ConversationFactory()
    phone_conversation = ConversationFactory()
    title_conversation.listing.property.name = "Sunrise Tower"
    title_conversation.listing.property.save(update_fields=["name", "updated_at"])
    phone_conversation.user.phone = "+998901112233"
    phone_conversation.user.save(update_fields=["phone", "updated_at"])

    title_response = api_client.get(
        "/api/v1/chat/conversations/?q=Sunrise&per_page=100",
        **_make_jwt(management),
    )
    phone_response = api_client.get(
        "/api/v1/chat/conversations/?q=901112233&per_page=100",
        **_make_jwt(management),
    )

    assert {item["id"] for item in _items(title_response)} == {title_conversation.id}
    assert {item["id"] for item in _items(phone_response)} == {phone_conversation.id}


@pytest.mark.django_db
def test_staff_reply_attributes_message_and_increments_user_unread_count(api_client, management):
    conversation = ConversationFactory()
    with patch("chat.services.conversations.notify"):
        response = api_client.post(
            _message_url(conversation),
            json.dumps({"text": "Welcome", "client_id": "staff-1"}),
            content_type="application/json",
            **_make_jwt(management),
        )

    assert response.status_code == 201
    message = Message.objects.get(conversation=conversation)
    conversation.refresh_from_db()
    assert message.sender_side == ChatSenderSide.STAFF
    assert message.sender_id == management.id
    assert conversation.user_unread_count == 1
    assert conversation.staff_unread_count == 0


@pytest.mark.django_db
def test_client_id_replay_returns_same_message_without_a_second_row(api_client, management):
    conversation = ConversationFactory()
    payload = json.dumps({"text": "First reply", "client_id": "retry-1"})
    with patch("chat.services.conversations.notify"):
        first = api_client.post(
            _message_url(conversation),
            payload,
            content_type="application/json",
            **_make_jwt(management),
        )
        second = api_client.post(
            _message_url(conversation),
            json.dumps({"text": "Retry with different text", "client_id": "retry-1"}),
            content_type="application/json",
            **_make_jwt(management),
        )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    assert Message.objects.filter(conversation=conversation, client_id="retry-1").count() == 1


@pytest.mark.django_db
def test_messages_use_id_cursor_when_a_message_is_inserted_between_polls(api_client, management):
    conversation = ConversationFactory()
    first = MessageFactory(conversation=conversation, sender_side=ChatSenderSide.USER)
    second = MessageFactory(conversation=conversation, sender_side=ChatSenderSide.USER)
    third = MessageFactory(conversation=conversation, sender_side=ChatSenderSide.USER)
    fourth = MessageFactory(conversation=conversation, sender_side=ChatSenderSide.USER)

    first_page = api_client.get(
        f"{_message_url(conversation)}?after_id={first.id}&limit=2",
        **_make_jwt(management),
    )
    assert first_page.status_code == 200
    assert [item["id"] for item in first_page.json()["data"]["messages"]] == [second.id, third.id]
    assert "page" not in first_page.json()["data"]
    assert "per_page" not in first_page.json()["data"]

    inserted = MessageFactory(conversation=conversation, sender_side=ChatSenderSide.USER)
    second_page = api_client.get(
        f"{_message_url(conversation)}?after_id={third.id}&limit=2",
        **_make_jwt(management),
    )

    assert second_page.status_code == 200
    assert [item["id"] for item in second_page.json()["data"]["messages"]] == [fourth.id, inserted.id]
    assert second_page.headers["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_deleted_by_user_conversation_remains_readable_but_staff_cannot_reply(api_client, management):
    conversation = ConversationFactory()
    conversation.user_deleted_at = timezone.now()
    conversation.save(update_fields=["user_deleted_at", "updated_at"])

    listing_response = api_client.get("/api/v1/chat/conversations/?per_page=100", **_make_jwt(management))
    detail_response = api_client.get(_conversation_url(conversation), **_make_jwt(management))
    reply_response = api_client.post(
        _message_url(conversation),
        json.dumps({"text": "Cannot send", "client_id": "read-only"}),
        content_type="application/json",
        **_make_jwt(management),
    )

    listed = {item["id"]: item for item in _items(listing_response)}
    assert listed[conversation.id]["deleted_by_user"] is True
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["is_read_only"] is True
    assert reply_response.status_code == 409


@pytest.mark.django_db
def test_block_and_unblock_update_the_management_state(api_client, management):
    conversation = ConversationFactory()

    blocked = api_client.post(f"{_conversation_url(conversation)}block/", **_make_jwt(management))
    unblocked = api_client.post(f"{_conversation_url(conversation)}unblock/", **_make_jwt(management))

    conversation.refresh_from_db()
    assert blocked.status_code == 200
    assert blocked.json()["data"]["is_blocked"] is True
    assert unblocked.status_code == 200
    assert unblocked.json()["data"]["is_blocked"] is False
    assert conversation.is_user_blocked is False


@pytest.mark.django_db
def test_delete_purges_conversation_from_staff_api_and_default_manager(api_client, management):
    conversation = ConversationFactory()
    response = api_client.delete(_conversation_url(conversation), **_make_jwt(management))

    assert response.status_code == 200
    assert response.json()["data"] == {"id": conversation.id, "deleted": True}
    assert api_client.get(_conversation_url(conversation), **_make_jwt(management)).status_code == 404
    assert not Conversation.objects.filter(pk=conversation.pk).exists()


@pytest.mark.django_db
def test_read_advances_staff_watermark_seen_by_the_other_side(api_client, management):
    conversation = ConversationFactory()
    user_message, _ = send_message(
        conversation,
        sender=conversation.user,
        side=ChatSenderSide.USER,
        text="Question",
    )

    response = api_client.post(
        f"{_conversation_url(conversation)}read/",
        json.dumps({"up_to_message_id": user_message.id}),
        content_type="application/json",
        **_make_jwt(management),
    )

    conversation.refresh_from_db()
    assert response.status_code == 200
    assert conversation.staff_last_read_message_id == user_message.id
    assert response.json()["data"]["staff_last_read_message_id"] == user_message.id


@pytest.mark.django_db
def test_reports_can_be_listed_and_resolved(api_client, management):
    unresolved = ConversationReportFactory(reason=ChatReportReason.SPAM)
    resolved = ConversationReportFactory(reason=ChatReportReason.ABUSE, resolved_at=timezone.now())

    pending_response = api_client.get("/api/v1/chat/reports/?resolved=false&per_page=100", **_make_jwt(management))
    resolved_response = api_client.get(
        "/api/v1/chat/reports/?resolved=true&per_page=100",
        **_make_jwt(management),
    )
    resolve_response = api_client.post(
        f"/api/v1/chat/reports/{unresolved.id}/resolve/",
        **_make_jwt(management),
    )

    assert {item["id"] for item in _items(pending_response)} == {unresolved.id}
    assert {item["id"] for item in _items(resolved_response)} == {resolved.id}
    assert resolve_response.status_code == 200
    unresolved.refresh_from_db()
    assert unresolved.resolved_at is not None
    assert unresolved.resolved_by_id == management.id
