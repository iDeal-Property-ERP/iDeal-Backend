import uuid

from account.models import User
from django.db import transaction
from django.utils import timezone
from notification.models import DeviceToken, NotificationPreference


class AccountDeletionService:
    """Anonymize an account without cascading into protected operational history."""

    @staticmethod
    def delete_account(user: User) -> None:
        avatar_name = user.avatar.name if user.avatar else None
        avatar_storage = user.avatar.storage if user.avatar else None
        deleted_at = timezone.now()
        anonymized_id = uuid.uuid4().hex

        with transaction.atomic():
            DeviceToken.objects.filter(user=user).hard_delete()
            NotificationPreference.objects.filter(user=user).hard_delete()

            # Do not call user.delete(): django-softdelete recursively traverses
            # reverse relations and protected business records must be retained.
            user.username = f"deleted-{anonymized_id}"
            user.email = f"deleted-{anonymized_id}@deleted.ideal.local"
            user.phone = None
            user.first_name = "Deleted user"
            user.last_name = None
            user.patronymic = None
            user.nationality = None
            user.telegram_id = None
            user.avatar = None
            user.is_active = False
            user.is_verified = False
            user.must_change_password = False
            user.set_unusable_password()
            user.deleted_at = deleted_at
            user.restored_at = None
            user.transaction_id = uuid.uuid4()
            user.save(
                update_fields=[
                    "username",
                    "email",
                    "phone",
                    "first_name",
                    "last_name",
                    "patronymic",
                    "nationality",
                    "telegram_id",
                    "avatar",
                    "is_active",
                    "is_verified",
                    "must_change_password",
                    "password",
                    "deleted_at",
                    "restored_at",
                    "transaction_id",
                    "updated_at",
                ]
            )

            if avatar_name and avatar_storage:
                transaction.on_commit(lambda: avatar_storage.delete(avatar_name))
