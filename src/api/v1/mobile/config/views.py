from http import HTTPStatus
from typing import Any

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from mobile_config.models import MobileUpdatePolicy
from mobile_config.utils import is_valid_semver, parse_semver

from api.v1.mobile.config.schemas import MobileMapConfigOutput, MobileVersionConfigOutput
from core.api.views import BaseController
from core.constants import DevicePlatform
from core.utils.map_obfuscator import obfuscate_map_token


class MobileMapConfigView(BaseController):
    auth = ()

    def get(self) -> dict:
        provider = getattr(settings, "MAP_DEFAULT_PROVIDER", "yandex").lower()
        if provider == "google":
            token = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
        else:
            provider = "yandex"
            token = getattr(settings, "YANDEX_MAPKIT_API_KEY", "")

        secret = getattr(settings, "MAP_OBFUSCATION_SECRET", "")
        obfuscated_token = obfuscate_map_token(token, secret) if token and secret else ""

        data = MobileMapConfigOutput(
            provider=provider,  # type: ignore[arg-type]
            token=obfuscated_token,
        ).model_dump(mode="json")
        return self.ok(data)


class MobileVersionConfigView(BaseController):
    auth = ()

    def get(self) -> Any:
        req: Any = getattr(self, "request", None)
        headers = getattr(req, "headers", {}) if req else {}
        meta = getattr(req, "META", {}) if req else {}

        platform_header = headers.get("X-App-Platform") or meta.get("HTTP_X_APP_PLATFORM")
        version_header = headers.get("X-App-Version") or meta.get("HTTP_X_APP_VERSION")

        if not platform_header or not version_header:
            return self.fail(
                error=str(_("Missing required headers: X-App-Platform and X-App-Version")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        platform = str(platform_header).strip().lower()
        if platform not in (DevicePlatform.ANDROID, DevicePlatform.IOS):
            return self.fail(
                error=str(_("Invalid X-App-Platform header. Must be 'android' or 'ios'.")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        current_version = str(version_header).strip()
        if not is_valid_semver(current_version):
            return self.fail(
                error=str(_("Invalid X-App-Version header. Must follow strict MAJOR.MINOR.PATCH format.")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        try:
            installed_semver = parse_semver(current_version)
        except ValueError:
            return self.fail(
                error=str(_("Invalid X-App-Version header.")),
                message=str(_("Validation error")),
                status_code=HTTPStatus.BAD_REQUEST,
            )

        policy = MobileUpdatePolicy.objects.filter(platform=platform, is_active=True).first()

        if not policy:
            data = MobileVersionConfigOutput(
                update_type="none",
                current_version=current_version,
                latest_version=None,
                store_url=None,
            )
        else:
            try:
                latest_semver = parse_semver(policy.latest_version)
            except ValueError:
                data = MobileVersionConfigOutput(
                    update_type="none",
                    current_version=current_version,
                    latest_version=None,
                    store_url=None,
                )
                response = self.ok(data, status_code=HTTPStatus.OK)
                response["Cache-Control"] = "no-store"
                return response

            if installed_semver >= latest_semver:
                data = MobileVersionConfigOutput(
                    update_type="none",
                    current_version=current_version,
                    latest_version=policy.latest_version,
                    store_url=policy.store_url,
                )
            else:
                is_critical = False
                for critical_range in policy.critical_ranges.filter(is_active=True):
                    try:
                        min_semver = parse_semver(critical_range.minimum_version)
                        max_semver = parse_semver(critical_range.maximum_version)
                        if min_semver <= installed_semver <= max_semver:
                            is_critical = True
                            break
                    except ValueError:
                        continue

                update_type = "critical" if is_critical else "normal"
                data = MobileVersionConfigOutput(
                    update_type=update_type,
                    current_version=current_version,
                    latest_version=policy.latest_version,
                    store_url=policy.store_url,
                )

        response = self.ok(data, status_code=HTTPStatus.OK)
        response["Cache-Control"] = "no-store"
        return response
