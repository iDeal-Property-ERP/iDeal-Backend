import os
from typing import Final

CUSTOM_ALPHABET: Final[str] = "9876543210zyxwvutsrqponmlkjihgfedcbaZYXWVUTSRQPONMLKJIHGFEDCBA-_"
_REVERSE_ALPHABET: Final[dict[str, int]] = {char: idx for idx, char in enumerate(CUSTOM_ALPHABET)}
MAGIC_BYTE: Final[int] = 0x5B
NONCE_SIZE: Final[int] = 8


def _custom_base_encode(data: bytes) -> str:
    """Encode bytes using custom 64-char dictionary without padding."""
    result: list[str] = []
    length = len(data)
    i = 0
    while i < length:
        b0 = data[i]
        b1 = data[i + 1] if i + 1 < length else 0
        b2 = data[i + 2] if i + 2 < length else 0

        chunk = (b0 << 16) | (b1 << 8) | b2

        result.append(CUSTOM_ALPHABET[(chunk >> 18) & 0x3F])
        result.append(CUSTOM_ALPHABET[(chunk >> 12) & 0x3F])

        if i + 1 < length:
            result.append(CUSTOM_ALPHABET[(chunk >> 6) & 0x3F])
        if i + 2 < length:
            result.append(CUSTOM_ALPHABET[chunk & 0x3F])

        i += 3
    return "".join(result)


def _custom_base_decode(text: str) -> bytes:
    """Decode custom 64-char dictionary string back to raw bytes."""
    clean_text = text.strip()
    if not clean_text:
        return b""

    for char in clean_text:
        if char not in _REVERSE_ALPHABET:
            raise ValueError(f"Invalid character in encoded payload: {char}")

    result = bytearray()
    length = len(clean_text)
    i = 0
    while i < length:
        rem = length - i
        if rem == 1:
            raise ValueError("Truncated base encoding")

        c0 = _REVERSE_ALPHABET[clean_text[i]]
        c1 = _REVERSE_ALPHABET[clean_text[i + 1]]
        c2 = _REVERSE_ALPHABET[clean_text[i + 2]] if rem > 2 else 0
        c3 = _REVERSE_ALPHABET[clean_text[i + 3]] if rem > 3 else 0

        chunk = (c0 << 18) | (c1 << 12) | (c2 << 6) | c3

        result.append((chunk >> 16) & 0xFF)
        if rem > 2:
            result.append((chunk >> 8) & 0xFF)
        if rem > 3:
            result.append(chunk & 0xFF)

        i += 4
    return bytes(result)


def _seed_state(secret: str, nonce: bytes) -> int:
    """Derive initial 32-bit PRNG state from secret key and dynamic nonce."""
    h = 0x811C9DC5
    for b in secret.encode("utf-8") + nonce:
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def _generate_keystream(state: int, length: int) -> list[int]:
    """Generate deterministic pseudo-random keystream bytes."""
    stream: list[int] = []
    current = state
    for _ in range(length):
        current = (current * 1103515245 + 12345) & 0xFFFFFFFF
        stream.append((current >> 16) & 0xFF)
    return stream


def obfuscate_map_token(token: str, secret: str, *, nonce: bytes | None = None) -> str:
    """Obfuscate an API token with a non-standard dynamic multi-layer transformation."""
    if not token:
        return ""

    if nonce is None:
        nonce = os.urandom(NONCE_SIZE)
    elif len(nonce) != NONCE_SIZE:
        raise ValueError(f"Nonce must be exactly {NONCE_SIZE} bytes")

    token_bytes = token.encode("utf-8")
    length = len(token_bytes)
    if length > 0xFFFF:
        raise ValueError("Token length exceeds maximum supported size (65535 bytes)")

    len_high = (length >> 8) & 0xFF
    len_low = length & 0xFF

    checksum = MAGIC_BYTE ^ len_high ^ len_low
    for b in token_bytes:
        checksum ^= b

    payload = bytearray([MAGIC_BYTE, len_high, len_low]) + token_bytes + bytes([checksum])
    payload_len = len(payload)

    state = _seed_state(secret, nonce)
    keystream = _generate_keystream(state, payload_len)

    scrambled = bytearray(payload_len)
    for i in range(payload_len):
        p = payload[i]
        k = keystream[i]
        # 1. Rolling XOR with keystream and index polynomial
        x = p ^ k ^ ((i * 37 + 13) & 0xFF)
        # 2. Nibble swap
        n = ((x << 4) & 0xF0) | ((x >> 4) & 0x0F)
        # 3. Dynamic rotation left by (1 to 4 bits) based on nonce
        shift = (nonce[i % NONCE_SIZE] & 0x03) + 1
        r = ((n << shift) & 0xFF) | (n >> (8 - shift))
        # 4. Modulo addition
        scrambled[i] = (r + 0x2A) & 0xFF

    raw_data = nonce + bytes(scrambled)
    return _custom_base_encode(raw_data)


def deobfuscate_map_token(payload: str, secret: str) -> str:
    """De-obfuscate payload back into the original API token string."""
    if not payload:
        return ""

    raw_data = _custom_base_decode(payload)
    if len(raw_data) < NONCE_SIZE + 4:
        raise ValueError("Payload is too short to be valid")

    nonce = raw_data[:NONCE_SIZE]
    scrambled = raw_data[NONCE_SIZE:]
    payload_len = len(scrambled)

    state = _seed_state(secret, nonce)
    keystream = _generate_keystream(state, payload_len)

    unscrambled = bytearray(payload_len)
    for i in range(payload_len):
        s = scrambled[i]
        # Reverse 4. Modulo subtraction
        r = (s - 0x2A) & 0xFF
        # Reverse 3. Dynamic rotation right
        shift = (nonce[i % NONCE_SIZE] & 0x03) + 1
        n = (r >> shift) | ((r << (8 - shift)) & 0xFF)
        # Reverse 2. Nibble swap (self-inverse)
        x = ((n << 4) & 0xF0) | ((n >> 4) & 0x0F)
        # Reverse 1. Rolling XOR
        k = keystream[i]
        unscrambled[i] = x ^ k ^ ((i * 37 + 13) & 0xFF)

    if unscrambled[0] != MAGIC_BYTE:
        raise ValueError("Invalid magic byte in decrypted payload")

    length = (unscrambled[1] << 8) | unscrambled[2]
    if len(unscrambled) != 3 + length + 1:
        raise ValueError("Payload length mismatch")

    token_bytes = bytes(unscrambled[3 : 3 + length])
    expected_checksum = unscrambled[3 + length]

    calc_checksum = MAGIC_BYTE ^ unscrambled[1] ^ unscrambled[2]
    for b in token_bytes:
        calc_checksum ^= b

    if calc_checksum != expected_checksum:
        raise ValueError("Checksum verification failed")

    return token_bytes.decode("utf-8")
