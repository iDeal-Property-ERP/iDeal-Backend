import pytest

from core.utils.map_obfuscator import (
    _custom_base_decode,
    _custom_base_encode,
    deobfuscate_map_token,
    obfuscate_map_token,
)

SECRET = "iDeal-Test-Map-Secret-2025!"
KNOWN_NONCE = b"\x01\x02\x03\x04\x05\x06\x07\x08"


def test_custom_base_encode_decode():
    data = b"Hello, World! 12345"
    encoded = _custom_base_encode(data)
    decoded = _custom_base_decode(encoded)
    assert decoded == data


def test_custom_base_invalid_chars():
    with pytest.raises(ValueError, match="Invalid character"):
        _custom_base_decode("invalid+char=")


def test_custom_base_truncated():
    with pytest.raises(ValueError, match="Truncated base encoding"):
        _custom_base_decode("a")


def test_roundtrip_tokens():
    tokens = [
        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "AIzaSyD-1234567890abcdefghijklmnopqrst",
        "simple_key",
        "X",
        "A" * 200,
        "token_with_utf8_🔥_test",
    ]
    for token in tokens:
        obfuscated = obfuscate_map_token(token, SECRET)
        assert obfuscated != token
        recovered = deobfuscate_map_token(obfuscated, SECRET)
        assert recovered == token


def test_different_nonces_produce_different_ciphertexts():
    token = "AIzaSyD-test-google-maps-api-key"
    obf1 = obfuscate_map_token(token, SECRET)
    obf2 = obfuscate_map_token(token, SECRET)
    assert obf1 != obf2
    assert deobfuscate_map_token(obf1, SECRET) == token
    assert deobfuscate_map_token(obf2, SECRET) == token


def test_deterministic_fixed_nonce_vector():
    token = "test-yandex-api-key-123"
    obfuscated = obfuscate_map_token(token, SECRET, nonce=KNOWN_NONCE)
    # Ensure exact consistency
    obfuscated2 = obfuscate_map_token(token, SECRET, nonce=KNOWN_NONCE)
    assert obfuscated == obfuscated2
    assert deobfuscate_map_token(obfuscated, SECRET) == token


def test_invalid_secret_fails_deobfuscation():
    token = "super_secret_token"
    obfuscated = obfuscate_map_token(token, SECRET)
    with pytest.raises(ValueError):
        deobfuscate_map_token(obfuscated, "wrong-secret-key")


def test_corrupted_payload_fails():
    token = "test_token_123"
    obfuscated = obfuscate_map_token(token, SECRET)
    # Alter character in middle
    corrupted = obfuscated[:10] + ("z" if obfuscated[10] != "z" else "y") + obfuscated[11:]
    with pytest.raises(ValueError):
        deobfuscate_map_token(corrupted, SECRET)


def test_empty_token():
    assert obfuscate_map_token("", SECRET) == ""
    assert deobfuscate_map_token("", SECRET) == ""
