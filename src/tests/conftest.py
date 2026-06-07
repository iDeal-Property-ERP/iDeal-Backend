import sys
from pathlib import Path

import pytest

_src_apps = Path(__file__).resolve().parent.parent / "apps"
if str(_src_apps) not in sys.path:
    sys.path.insert(0, str(_src_apps))

from tests.factories import DistrictFactory, OwnerFactory, PropertyFactory, UserFactory  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "unit: marks tests as unit tests")


@pytest.fixture
def api_client():
    from django.test import Client

    return Client()


@pytest.fixture
def user():
    return UserFactory()


@pytest.fixture
def owner():
    return OwnerFactory()


@pytest.fixture
def tenant():
    from tests.factories import TenantFactory

    return TenantFactory()


@pytest.fixture
def district():
    return DistrictFactory()


@pytest.fixture
def property_obj(district, owner):
    return PropertyFactory(district=district, owner=owner)


@pytest.fixture
def jwt_header(user):
    from datetime import UTC, datetime, timedelta

    import jwt
    from django.conf import settings

    payload = {
        "sub": str(user.id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "token_type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}
