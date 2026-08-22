import re

SEMVER_REGEX = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def is_valid_semver(version: str) -> bool:
    if not isinstance(version, str):
        return False
    return bool(SEMVER_REGEX.match(version.strip()))


def parse_semver(version: str) -> tuple[int, int, int]:
    if not isinstance(version, str):
        raise ValueError(f"Version must be a string, got {type(version).__name__}")
    cleaned = version.strip()
    match = SEMVER_REGEX.match(cleaned)
    if not match:
        raise ValueError(f"Invalid semantic version '{version}'. Must follow strict MAJOR.MINOR.PATCH format.")
    try:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    except (ValueError, IndexError) as err:
        raise ValueError(f"Invalid semantic version '{version}'.") from err


def compare_semver(v1: str, v2: str) -> int:
    t1 = parse_semver(v1)
    t2 = parse_semver(v2)
    if t1 < t2:
        return -1
    if t1 > t2:
        return 1
    return 0
