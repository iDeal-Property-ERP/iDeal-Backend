import pytest
from pydantic import ValidationError

from api.v1.mobile.home.schemas import MobileHomeMapQuery, parse_bbox


@pytest.mark.parametrize(
    "value",
    [
        "",
        "69,41,70",
        "69,41,70,42,43",
        "west,41,70,42",
        "nan,41,70,42",
        "69,41,inf,42",
        "-181,41,70,42",
        "69,-91,70,42",
        "69,41,181,42",
        "69,41,70,91",
        "70,41,69,42",
        "69,42,70,41",
        "69,41,69,42",
        "69,41,70,41",
    ],
)
def test_map_query_rejects_invalid_bbox(value):
    with pytest.raises(ValidationError):
        MobileHomeMapQuery(bbox=value)


def test_map_query_requires_bbox():
    with pytest.raises(ValidationError):
        MobileHomeMapQuery()


def test_parse_bbox_returns_validated_coordinates():
    assert parse_bbox("69,41,70,42") == (69.0, 41.0, 70.0, 42.0)
