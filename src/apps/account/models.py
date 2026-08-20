from account import managers
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models

from core.constants import UserRole
from core.models import SoftDeleteModel, TimestampedModel


class User(AbstractBaseUser, TimestampedModel, SoftDeleteModel):
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    patronymic = models.CharField(max_length=100, blank=True, null=True)

    username = models.CharField(max_length=150, unique=True)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True, default=None)
    avatar = models.ImageField(upload_to="users/avatars/", blank=True, null=True)

    role = models.CharField(max_length=20, choices=UserRole.choices, default=UserRole.MANAGEMENT)
    is_verified = models.BooleanField(default=False)
    nationality = models.CharField(max_length=50, blank=True, null=True)
    telegram_id = models.CharField(max_length=100, blank=True, null=True)

    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    must_change_password = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["first_name"]

    objects = managers.UserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.first_name} (@{self.get_username()})"

    def get_navigation_title(self):
        return f"{self.first_name} {self.last_name}"

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    def save(self, *args, **kwargs):
        self._ensure_password()
        return super().save(*args, **kwargs)

    def _ensure_password(self):
        from django.contrib.auth.hashers import identify_hasher, is_password_usable, make_password

        if self.password and is_password_usable(self.password):
            try:
                identify_hasher(self.password)
            except ValueError:
                self.password = make_password(self.password)


class TokenBlacklist(TimestampedModel):
    """Revoked JWT ids (jti). A token whose jti is listed here is rejected by the
    auth layer even if its signature and expiry are still valid. Populated on
    logout and on refresh-token rotation (the consumed refresh token is revoked)."""

    jti = models.CharField(max_length=255, unique=True, db_index=True)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the underlying token expires; rows past this are safe to prune.",
    )

    class Meta:
        db_table = "token_blacklist"

    def __str__(self):
        return str(self.jti)
