"""Reusable validation for property floor information."""

from django.utils.translation import gettext_lazy as _

FLOOR_EXCEEDS_TOTAL_FLOORS_MESSAGE = _("Floor cannot be greater than total floors.")


def validate_floor_bounds(floor: int | None, total_floors: int | None) -> None:
    """Reject a floor that exceeds a known building height.

    Partial API inputs may omit either side, so callers that update an existing
    property should pass merged persisted and submitted values.
    """
    if floor is not None and total_floors is not None and floor > total_floors:
        raise ValueError(FLOOR_EXCEEDS_TOTAL_FLOORS_MESSAGE)
