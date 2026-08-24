"""Read-only presentation facts shared by public and mobile listing APIs."""

from django.utils.translation import gettext_lazy as _

VERIFICATION_CHECKLIST = (
    {"key": "ownership", "label": _("Official ownership check")},
    {"key": "team", "label": _("Verified by iDeal team")},
    {"key": "contract", "label": _("In-app contract & payments")},
    {"key": "managed", "label": _("Managed end-to-end")},
)
RESPONSE_TIME = _("Usually responds within 1 hour")


def verification_checklist(property_) -> list[dict[str, str]]:
    """Return presentation data only; callers must prefetch their property."""
    if not property_.is_verified:
        return []
    return [{"key": item["key"], "label": str(item["label"])} for item in VERIFICATION_CHECKLIST]
