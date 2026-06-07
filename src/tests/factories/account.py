import factory
from account.models import User

from core.constants import UserRole


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    phone = factory.Sequence(lambda n: f"+998{n:09d}")
    role = UserRole.MANAGEMENT
    is_verified = True
    is_active = True


class OwnerFactory(UserFactory):
    role = UserRole.OWNER


class TenantFactory(UserFactory):
    role = UserRole.TENANT


class AgentFactory(UserFactory):
    role = UserRole.AGENT
