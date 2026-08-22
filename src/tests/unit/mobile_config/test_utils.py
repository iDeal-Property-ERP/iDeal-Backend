import pytest
from mobile_config.utils import compare_semver, is_valid_semver, parse_semver


@pytest.mark.unit
class TestSemverUtils:
    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("0.0.0", True),
            ("1.0.0", True),
            ("0.1.0", True),
            ("0.0.1", True),
            ("10.20.30", True),
            ("999.999.999", True),
            ("1.0", False),
            ("1", False),
            ("1.0.0.0", False),
            ("v1.0.0", False),
            ("1.0.0-alpha", False),
            ("1.0.0+1", False),
            ("01.0.0", False),
            ("1.01.0", False),
            ("1.0.01", False),
            ("-1.0.0", False),
            ("1.-1.0", False),
            ("", False),
            ("   ", False),
            (None, False),
            (123, False),
        ],
    )
    def test_is_valid_semver(self, version, expected):
        assert is_valid_semver(version) is expected

    @pytest.mark.parametrize(
        ("version", "expected"),
        [
            ("0.0.0", (0, 0, 0)),
            ("1.2.3", (1, 2, 3)),
            ("10.200.3000", (10, 200, 3000)),
        ],
    )
    def test_parse_semver_valid(self, version, expected):
        assert parse_semver(version) == expected

    @pytest.mark.parametrize(
        "version",
        [
            "v1.0.0",
            "1.0",
            "1.0.0.0",
            "1.0.0-rc1",
            "abc",
            "",
            None,
        ],
    )
    def test_parse_semver_invalid(self, version):
        with pytest.raises(ValueError, match="Invalid semantic version|Version must be a string"):
            parse_semver(version)

    @pytest.mark.parametrize(
        ("v1", "v2", "expected"),
        [
            ("1.0.0", "1.0.0", 0),
            ("0.1.0", "0.1.0", 0),
            ("1.0.0", "1.0.1", -1),
            ("1.0.1", "1.0.0", 1),
            ("1.1.0", "1.2.0", -1),
            ("1.2.0", "1.1.0", 1),
            ("1.0.0", "2.0.0", -1),
            ("2.0.0", "1.0.0", 1),
            ("0.9.9", "1.0.0", -1),
            ("1.0.0", "0.9.9", 1),
            ("1.10.0", "1.2.0", 1),
            ("1.2.0", "1.10.0", -1),
        ],
    )
    def test_compare_semver(self, v1, v2, expected):
        assert compare_semver(v1, v2) == expected
