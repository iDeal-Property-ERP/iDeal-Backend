from django.conf import settings


def test_database_connection_persistence_disabled_for_asgi():
    """Persistent DB connections must be disabled under ASGI to avoid connection leaks."""
    default_db = settings.DATABASES["default"]
    assert default_db["CONN_MAX_AGE"] == 0
    assert default_db["CONN_HEALTH_CHECKS"] is True
