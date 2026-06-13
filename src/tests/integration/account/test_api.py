import pytest


@pytest.mark.django_db
class TestUserMeAPI:
    def test_get_current_user(self, api_client, jwt_header):
        response = api_client.get("/api/v1/users/me/", **jwt_header)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["id"] is not None
        assert data["username"] is not None
        assert data["email"] is not None
        assert data["role"] is not None

    def test_get_current_user_requires_auth(self, api_client):
        response = api_client.get("/api/v1/users/me/")
        assert response.status_code == 401

    def test_get_current_user_has_all_fields(self, api_client, jwt_header):
        response = api_client.get("/api/v1/users/me/", **jwt_header)
        body = response.json()
        data = body["data"]
        expected_fields = {
            "id",
            "first_name",
            "last_name",
            "patronymic",
            "username",
            "phone",
            "email",
            "role",
            "is_verified",
            "nationality",
            "telegram_id",
            "created_at",
            "updated_at",
        }
        assert set(data.keys()) == expected_fields
