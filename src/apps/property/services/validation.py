"""Reusable validation for property attributes."""

from django.utils.translation import gettext_lazy as _

FLOOR_EXCEEDS_TOTAL_FLOORS_MESSAGE = _("Floor cannot be greater than total floors.")
LANDMARK_MAX_WORDS = 5
LANDMARK_MAX_CHARS = 100
LANDMARK_TOO_MANY_WORDS_MESSAGE = _("Landmark cannot exceed 5 words.")
LANDMARK_TOO_LONG_MESSAGE = _("Landmark cannot exceed 100 characters.")


def validate_floor_bounds(floor: int | None, total_floors: int | None) -> None:
    """Reject a floor that exceeds a known building height.

    Partial API inputs may omit either side, so callers that update an existing
    property should pass merged persisted and submitted values.
    """
    if floor is not None and total_floors is not None and floor > total_floors:
        raise ValueError(FLOOR_EXCEEDS_TOTAL_FLOORS_MESSAGE)


def validate_and_normalize_landmark(value: str | None) -> str | None:
    """Normalize and validate an optional property landmark.

    - Trims and collapses whitespace.
    - Converts blank / whitespace-only values to None.
    - Rejects values exceeding 5 whitespace-separated words.
    - Rejects normalized values exceeding 100 characters.
    """
    if value is None:
        return None

    words = value.split()
    if not words:
        return None

    if len(words) > LANDMARK_MAX_WORDS:
        raise ValueError(LANDMARK_TOO_MANY_WORDS_MESSAGE)

    normalized = " ".join(words)
    if len(normalized) > LANDMARK_MAX_CHARS:
        raise ValueError(LANDMARK_TOO_LONG_MESSAGE)

    return normalized
