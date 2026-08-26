from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from mobile_config.utils import is_valid_semver, parse_semver

from core.constants import DevicePlatform
from core.models import TimestampedModel


class MobileUpdatePolicy(TimestampedModel):
    platform = models.CharField(
        max_length=20,
        choices=DevicePlatform.choices,
        db_index=True,
        verbose_name=_("Platform"),
    )
    latest_version = models.CharField(
        max_length=32,
        verbose_name=_("Latest Version"),
    )
    store_url = models.URLField(
        max_length=500,
        verbose_name=_("Store URL"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Is Active"),
    )

    class Meta:
        verbose_name = _("Mobile Update Policy")
        verbose_name_plural = _("Mobile Update Policies")
        db_table = "mobile_update_policies"
        constraints = [
            models.UniqueConstraint(
                fields=["platform"],
                condition=models.Q(is_active=True),
                name="unique_active_policy_per_platform",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        platform_display = self.get_platform_display()  # type: ignore[attr-defined]
        status = "active" if self.is_active else "inactive"
        return f"{platform_display} v{self.latest_version} ({status})"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        latest_version = str(self.latest_version or "").strip()
        if not latest_version or not is_valid_semver(latest_version):
            errors["latest_version"] = str(
                _("Latest version must follow strict MAJOR.MINOR.PATCH format (e.g. 1.0.0).")
            )

        store_url = str(self.store_url or "").strip()
        if not store_url or not store_url.startswith("https://"):
            errors["store_url"] = str(_("Store URL must be a valid HTTPS URL."))

        if errors:
            raise ValidationError(errors)


class MobileCriticalUpdateRange(TimestampedModel):
    policy = models.ForeignKey(
        MobileUpdatePolicy,
        on_delete=models.CASCADE,
        related_name="critical_ranges",
        verbose_name=_("Policy"),
    )
    minimum_version = models.CharField(
        max_length=32,
        verbose_name=_("Minimum Version"),
    )
    maximum_version = models.CharField(
        max_length=32,
        verbose_name=_("Maximum Version"),
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        verbose_name=_("Is Active"),
    )

    class Meta:
        verbose_name = _("Mobile Critical Update Range")
        verbose_name_plural = _("Mobile Critical Update Ranges")
        db_table = "mobile_critical_update_ranges"
        ordering = ["minimum_version", "-created_at"]

    def __str__(self) -> str:
        policy_platform: Any = getattr(self.policy, "platform", "unknown")
        return f"{policy_platform}: [{self.minimum_version} .. {self.maximum_version}]"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}

        min_str = str(self.minimum_version or "").strip()
        max_str = str(self.maximum_version or "").strip()

        min_valid = bool(min_str and is_valid_semver(min_str))
        max_valid = bool(max_str and is_valid_semver(max_str))

        if not min_valid:
            errors["minimum_version"] = str(
                _("Minimum version must follow strict MAJOR.MINOR.PATCH format (e.g. 1.0.0).")
            )
        if not max_valid:
            errors["maximum_version"] = str(
                _("Maximum version must follow strict MAJOR.MINOR.PATCH format (e.g. 1.0.0).")
            )

        if min_valid and max_valid:
            try:
                min_semver = parse_semver(min_str)
                max_semver = parse_semver(max_str)
                if min_semver > max_semver:
                    errors["maximum_version"] = str(
                        _("Maximum version must be greater than or equal to minimum version.")
                    )
            except ValueError:
                errors["maximum_version"] = str(_("Invalid version range."))

        if errors:
            raise ValidationError(errors)
