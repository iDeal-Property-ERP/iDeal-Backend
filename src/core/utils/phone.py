import re

UZBEKISTAN_PHONE_PATTERN = re.compile(r"\+998\d{9}\Z")


def normalize_uzbekistan_phone(phone: str) -> str:
    """Normalize and validate an Uzbekistan mobile phone number."""
    if not isinstance(phone, str):
        raise ValueError("phone must be a string")

    normalized = re.sub(r"[\s\-()]", "", phone.strip())
    if normalized.startswith("00"):
        normalized = f"+{normalized[2:]}"
    elif not normalized.startswith("+"):
        normalized = f"+{normalized}"

    if not UZBEKISTAN_PHONE_PATTERN.fullmatch(normalized):
        raise ValueError("invalid phone number")
    return normalized
