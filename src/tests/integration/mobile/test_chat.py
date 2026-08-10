import base64
import json
from datetime import timedelta

import pytest
from chat.models import Conversation, Message
from chat.services import mark_read
from django.core.files.uploadedfile import SimpleUploadedFile

from core.constants import ChatSenderSide, ListingStatus
from tests.factories import ConversationFactory, ListingFactory, MessageFactory, TenantFactory
from tests.integration.property.test_api import _make_jwt

ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _post(api_client, path, payload, **headers):
    return api_client.post(path, data=json.dumps(payload), content_type="application/json", **headers)


def _upload(api_client, path, *, name, content, content_type, client_id=None, **headers):
    data = {"image": SimpleUploadedFile(name, content, content_type=content_type)}
    if client_id is not None:
        data["client_id"] = client_id
    return api_client.post(path, data=data, **headers)


def _published_listing():
    listing = ListingFactory()
    listing.status = ListingStatus.PUBLISHED
    listing.save(update_fields=["status", "updated_at"])
    return listing


def _conversation(user):
    return ConversationFactory(user=user, listing=_published_listing())


@pytest.mark.django_db
class TestMobileChatOpenAndListAPI:
    base_url = "/api/v1/mobile/chat/"

    def test_open_or_get_is_idempotent(self, api_client):
        user = TenantFactory()
        listing = _published_listing()

        first = _post(
            api_client,
            f"{self.base_url}conversations/",
            {"listing_id": listing.id},
            **_make_jwt(user),
        )
        second = _post(
            api_client,
            f"{self.base_url}conversations/",
            {"listing_id": listing.id},
            **_make_jwt(user),
        )

        assert first.status_code == 201
        assert second.status_code == 200
        assert first.json()["data"]["id"] == second.json()["data"]["id"]
        assert Conversation.objects.filter(user=user, listing=listing).count() == 1

    def test_unpublished_listing_is_unavailable_and_open_requires_auth(self, api_client):
        user = TenantFactory()
        listing = _published_listing()
        listing.status = ListingStatus.DRAFT
        listing.save(update_fields=["status", "updated_at"])

        rejected = _post(
            api_client,
            f"{self.base_url}conversations/",
            {"listing_id": listing.id},
            **_make_jwt(user),
        )
        anonymous = _post(
            api_client,
            f"{self.base_url}conversations/",
            {"listing_id": listing.id},
        )

        assert rejected.status_code == 400
        assert anonymous.status_code == 401

    def test_list_is_scoped_and_archived_filter_round_trips(self, api_client):
        user = TenantFactory()
        other = TenantFactory()
        active = _conversation(user)
        archived = _conversation(user)
        other_conversation = _conversation(other)

        archived_response = api_client.post(
            f"{self.base_url}conversations/{archived.id}/archive/",
            **_make_jwt(user),
        )
        assert archived_response.status_code == 200

        active_list = api_client.get(
            f"{self.base_url}conversations/",
            {"page": 1, "per_page": 20},
            **_make_jwt(user),
        )
        archived_list = api_client.get(
            f"{self.base_url}conversations/",
            {"archived": "true", "page": 1, "per_page": 20},
            **_make_jwt(user),
        )

        assert active_list.status_code == 200
        assert archived_list.status_code == 200
        active_ids = {item["id"] for item in active_list.json()["data"]["page"]["object_list"]}
        archived_ids = {item["id"] for item in archived_list.json()["data"]["page"]["object_list"]}
        assert active_ids == {active.id}
        assert archived_ids == {archived.id}
        assert other_conversation.id not in active_ids | archived_ids


@pytest.mark.django_db
class TestMobileChatMessagesAPI:
    base_url = "/api/v1/mobile/chat/"

    def test_before_cursor_does_not_skip_or_duplicate_when_new_messages_are_appended(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)
        original = [
            MessageFactory(conversation=conversation, sender=conversation.user, sender_side=ChatSenderSide.USER)
            for _ in range(5)
        ]

        first = api_client.get(
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"before_id": original[-1].id, "limit": 2},
            **_make_jwt(user),
        )
        first_ids = [item["id"] for item in first.json()["data"]["messages"]]
        assert first.status_code == 200
        assert first_ids == [original[2].id, original[3].id]
        assert first.json()["data"]["has_more"] is True

        appended = MessageFactory(
            conversation=conversation,
            sender=conversation.user,
            sender_side=ChatSenderSide.USER,
        )
        second = api_client.get(
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"before_id": first_ids[0], "limit": 2},
            **_make_jwt(user),
        )
        second_ids = [item["id"] for item in second.json()["data"]["messages"]]

        assert second.status_code == 200
        assert second_ids == [original[0].id, original[1].id]
        assert set(first_ids + second_ids) == {message.id for message in original[:-1]}
        assert appended.id not in first_ids + second_ids
        assert len(first_ids + second_ids) == len(set(first_ids + second_ids))

    def test_after_cursor_returns_only_newer_messages_and_idle_poll_is_empty(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)
        first = MessageFactory(conversation=conversation, sender=conversation.user, sender_side=ChatSenderSide.USER)
        second = MessageFactory(conversation=conversation, sender=conversation.user, sender_side=ChatSenderSide.USER)

        newer = api_client.get(
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"after_id": first.id, "limit": 50},
            **_make_jwt(user),
        )
        idle = api_client.get(
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"after_id": second.id, "limit": 50},
            **_make_jwt(user),
        )
        offset = api_client.get(
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"page": 1},
            **_make_jwt(user),
        )

        assert newer.status_code == 200
        assert [item["id"] for item in newer.json()["data"]["messages"]] == [second.id]
        assert idle.status_code == 200
        assert idle.json()["data"]["messages"] == []
        assert idle.json()["data"]["conversation"]["id"] == conversation.id
        assert idle.headers["Cache-Control"] == "no-store"
        assert offset.status_code == 400

    def test_text_validation_and_client_id_replay(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)

        empty = _post(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"text": ""},
            **_make_jwt(user),
        )
        too_long = _post(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"text": "x" * 1025},
            **_make_jwt(user),
        )
        first = _post(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"text": "hello", "client_id": "mobile-1"},
            **_make_jwt(user),
        )
        replay = _post(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"text": "retry with different text", "client_id": "mobile-1"},
            **_make_jwt(user),
        )

        assert empty.status_code == 400
        assert too_long.status_code == 400
        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json()["data"]["id"] == first.json()["data"]["id"]
        assert Message.objects.filter(conversation=conversation, client_id="mobile-1").count() == 1

    def test_image_upload_accepts_chat_images_and_rejects_large_or_non_images(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)
        path = f"{self.base_url}conversations/{conversation.id}/messages/image/"

        happy = _upload(
            api_client,
            path,
            name="photo.png",
            content=ONE_PIXEL_PNG,
            content_type="image/png",
            client_id="image-1",
            **_make_jwt(user),
        )
        large = _upload(
            api_client,
            path,
            name="large.png",
            content=b"x" * (6 * 1024 * 1024),
            content_type="image/png",
            **_make_jwt(user),
        )
        pdf = _upload(
            api_client,
            path,
            name="document.pdf",
            content=b"%PDF-1.7",
            content_type="application/pdf",
            **_make_jwt(user),
        )

        assert happy.status_code == 201
        assert happy.json()["data"]["kind"] == "image"
        assert happy.json()["data"]["image_url"]
        assert large.status_code == 400
        assert pdf.status_code == 400

    def test_read_advances_user_watermark_and_mobile_poll_exposes_staff_watermark(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)
        staff = TenantFactory()
        staff_message = MessageFactory(
            conversation=conversation,
            sender=staff,
            sender_side=ChatSenderSide.STAFF,
        )

        marked = _post(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/read/",
            {"up_to_message_id": staff_message.id},
            **_make_jwt(user),
        )
        conversation.refresh_from_db()
        assert marked.status_code == 200
        assert conversation.user_last_read_message_id == staff_message.id

        own_message = MessageFactory(
            conversation=conversation,
            sender=conversation.user,
            sender_side=ChatSenderSide.USER,
        )
        mark_read(conversation, side=ChatSenderSide.STAFF, up_to_message_id=own_message.id)
        poll = api_client.get(
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"after_id": own_message.id},
            **_make_jwt(user),
        )
        assert poll.status_code == 200
        assert poll.json()["data"]["conversation"]["peer_last_read_message_id"] == own_message.id


@pytest.mark.django_db
class TestMobileChatActionsAndScopeAPI:
    base_url = "/api/v1/mobile/chat/"

    def test_archive_unarchive_and_mute_unmute_round_trip(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)
        path = f"{self.base_url}conversations/{conversation.id}"

        archived = api_client.post(f"{path}/archive/", **_make_jwt(user))
        unarchived = api_client.post(f"{path}/unarchive/", **_make_jwt(user))
        muted = api_client.post(f"{path}/mute/", **_make_jwt(user))
        unmuted = api_client.post(f"{path}/unmute/", **_make_jwt(user))

        assert archived.status_code == 200
        assert archived.json()["data"]["is_archived"] is True
        assert unarchived.status_code == 200
        assert unarchived.json()["data"]["is_archived"] is False
        assert muted.status_code == 200
        assert muted.json()["data"]["is_muted"] is True
        assert unmuted.status_code == 200
        assert unmuted.json()["data"]["is_muted"] is False

    def test_report_creates_a_report(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)

        response = _post(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/report/",
            {"reason": "spam", "note": "Suspicious listing"},
            **_make_jwt(user),
        )

        assert response.status_code == 201
        assert response.json()["data"]["id"]
        assert response.json()["data"]["reason"] == "spam"

    def test_read_only_conversation_allows_non_send_actions(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)
        conversation.is_user_blocked = True
        conversation.save(update_fields=["is_user_blocked", "updated_at"])

        blocked_send = _post(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/messages/",
            {"text": "blocked"},
            **_make_jwt(user),
        )
        marked_read = _post(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/read/",
            {},
            **_make_jwt(user),
        )
        archived = api_client.post(
            f"{self.base_url}conversations/{conversation.id}/archive/",
            **_make_jwt(user),
        )
        muted = api_client.post(
            f"{self.base_url}conversations/{conversation.id}/mute/",
            **_make_jwt(user),
        )
        deleted = api_client.delete(
            f"{self.base_url}conversations/{conversation.id}/",
            **_make_jwt(user),
        )

        assert blocked_send.status_code == 409
        assert marked_read.status_code == 200
        assert archived.status_code == 200
        assert muted.status_code == 200
        assert deleted.status_code == 200

    def test_delete_hides_conversation_but_keeps_row(self, api_client):
        user = TenantFactory()
        conversation = _conversation(user)

        deleted = api_client.delete(
            f"{self.base_url}conversations/{conversation.id}/",
            **_make_jwt(user),
        )
        hidden = api_client.get(
            f"{self.base_url}conversations/{conversation.id}/",
            **_make_jwt(user),
        )

        assert deleted.status_code == 200
        assert hidden.status_code == 404
        assert Conversation.global_objects.filter(pk=conversation.pk).exists()

    @pytest.mark.parametrize(
        ("method", "suffix", "payload"),
        [
            # Suffixes must keep the trailing slash: Django's APPEND_SLASH answers
            # a slashless path with a 301 before auth or scoping ever run.
            ("get", "/", None),
            ("get", "/messages/", None),
            ("post", "/messages/", {"text": "not mine"}),
            ("post", "/read/", {}),
            ("post", "/archive/", {}),
            ("post", "/unarchive/", {}),
            ("post", "/mute/", {}),
            ("post", "/unmute/", {}),
            ("post", "/report/", {"reason": "spam"}),
            ("delete", "/", None),
        ],
    )
    def test_other_user_gets_404_for_every_conversation_route(self, api_client, method, suffix, payload):
        owner = TenantFactory()
        other = TenantFactory()
        conversation = _conversation(owner)
        path = f"{self.base_url}conversations/{conversation.id}{suffix}"

        if method == "get":
            response = api_client.get(path, **_make_jwt(other))
        elif method == "delete":
            response = api_client.delete(path, **_make_jwt(other))
        else:
            response = _post(api_client, path, payload, **_make_jwt(other))

        assert response.status_code == 404

    def test_other_user_gets_404_for_image_route(self, api_client):
        owner = TenantFactory()
        other = TenantFactory()
        conversation = _conversation(owner)
        response = _upload(
            api_client,
            f"{self.base_url}conversations/{conversation.id}/messages/image/",
            name="photo.png",
            content=ONE_PIXEL_PNG,
            content_type="image/png",
            **_make_jwt(other),
        )
        assert response.status_code == 404


@pytest.mark.django_db
def test_every_mobile_chat_route_requires_authentication(api_client):
    user = TenantFactory()
    listing = _published_listing()
    conversation = _conversation(user)
    conversation_path = f"/api/v1/mobile/chat/conversations/{conversation.id}"
    unauthenticated_routes = [
        ("get", "/api/v1/mobile/chat/conversations/", None),
        ("post", "/api/v1/mobile/chat/conversations/", {"listing_id": listing.id}),
        ("get", "/api/v1/mobile/chat/summary/", None),
        ("get", f"{conversation_path}/", None),
        ("get", f"{conversation_path}/messages/", None),
        ("post", f"{conversation_path}/messages/", {"text": "hello"}),
        ("post", f"{conversation_path}/read/", {}),
        ("post", f"{conversation_path}/archive/", {}),
        ("post", f"{conversation_path}/unarchive/", {}),
        ("post", f"{conversation_path}/mute/", {}),
        ("post", f"{conversation_path}/unmute/", {}),
        ("post", f"{conversation_path}/report/", {"reason": "spam"}),
        ("delete", f"{conversation_path}/", None),
    ]

    for method, path, payload in unauthenticated_routes:
        if method == "get":
            response = api_client.get(path)
        elif method == "delete":
            response = api_client.delete(path)
        else:
            response = _post(api_client, path, payload)
        assert response.status_code == 401, path

    image_response = api_client.post(
        f"{conversation_path}/messages/image/",
        data={"image": SimpleUploadedFile("photo.png", ONE_PIXEL_PNG, content_type="image/png")},
    )
    assert image_response.status_code == 401


@pytest.mark.django_db
def test_summary_returns_unread_count_and_changed_ids(api_client):
    user = TenantFactory()
    conversation = _conversation(user)
    conversation.user_unread_count = 3
    conversation.save(update_fields=["user_unread_count", "updated_at"])
    since = (conversation.updated_at - timedelta(seconds=1)).isoformat()

    with_since = api_client.get(
        "/api/v1/mobile/chat/summary/",
        {"since": since},
        **_make_jwt(user),
    )
    without_since = api_client.get(
        "/api/v1/mobile/chat/summary/",
        **_make_jwt(user),
    )

    assert with_since.status_code == 200
    assert with_since.json()["data"]["total_unread"] == 3
    assert with_since.json()["data"]["changed_conversation_ids"] == [conversation.id]
    assert with_since.json()["data"]["server_time"]
    assert without_since.status_code == 200
    assert without_since.json()["data"]["total_unread"] == 3
    assert without_since.json()["data"]["changed_conversation_ids"] == []
