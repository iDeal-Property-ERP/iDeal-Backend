"""Reusable mock-image helpers shared by the seeder and the photo-backfill command.

Real-estate **listing** photos use LoremFlickr's keyword endpoint so each image matches its
room caption (kitchen, bedroom, …). A small fixed pool is fetched once and cached, so the total
number of network calls stays bounded no matter how many properties × photos are created. Any
failure falls back to a random Picsum photo, then to a generated solid-colour PNG, so callers
work offline and never hard-fail.
"""

import urllib.request
from io import BytesIO

from django.core.files.base import ContentFile

# (caption, LoremFlickr tags). Exteriors supply the cover (first) photo; interiors fill the rest.
_EXTERIORS = [
    ("Building exterior", "apartment,building"),
    ("Front facade", "facade,building"),
    ("Modern apartment block", "apartment,modern"),
    ("Residential building", "residential,building"),
    ("Courtyard view", "courtyard,apartment"),
    ("Street view", "street,building"),
    ("Evening exterior", "apartment,dusk"),
    ("Entrance lobby", "lobby,apartment"),
    ("Rooftop terrace", "rooftop,terrace"),
    ("Garden view", "garden,apartment"),
]
_INTERIORS = [
    ("Living room", "livingroom"),
    ("Bright living space", "livingroom,bright"),
    ("Modern kitchen", "kitchen,modern"),
    ("Kitchen", "kitchen"),
    ("Master bedroom", "bedroom"),
    ("Cozy bedroom", "bedroom,cozy"),
    ("Bathroom", "bathroom"),
    ("Ensuite bathroom", "bathroom,modern"),
    ("Balcony view", "balcony"),
    ("Dining area", "diningroom"),
    ("Hallway", "hallway,interior"),
    ("Home office", "homeoffice"),
    ("Walk-in closet", "closet,wardrobe"),
    ("Reading nook", "interior,cozy"),
]

# Process-wide cache: a given pool image is downloaded at most once per run.
_CACHE: dict[str, bytes] = {}


def _download(url, *, timeout=12):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ideal mock images)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (trusted URL)
        return response.read()


def _placeholder_bytes(rng):
    """A solid-colour PNG used when every remote source is unreachable."""
    from PIL import Image

    color = (rng.randint(60, 200), rng.randint(60, 200), rng.randint(60, 200))
    buffer = BytesIO()
    Image.new("RGB", (800, 600), color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def _cached_bytes(url, *, fallback_seed, rng):
    """Image bytes for ``url`` (cached); falls back to a random Picsum photo, then a PNG."""
    if url in _CACHE:
        return _CACHE[url]
    try:
        data = _download(url)
    except Exception:  # noqa: BLE001 — try a random Picsum photo before the offline placeholder
        try:
            data = _download(f"https://picsum.photos/seed/{fallback_seed}/800/600")
        except Exception:  # noqa: BLE001 — any network/IO error falls back to a placeholder
            data = _placeholder_bytes(rng)
    _CACHE[url] = data
    return data


def real_estate_photo_set(count, *, rng):
    """Return ``count`` ``(ContentFile, caption)`` apartment photos — cover (exterior) first.

    Each photo's image matches its caption via room-type LoremFlickr tags, drawn from a fixed,
    cached pool so repeated calls stay cheap. ``count`` is clamped to ``>= 1``.
    """
    count = max(count, 1)
    cover_idx = rng.randrange(len(_EXTERIORS))
    chosen = [(*_EXTERIORS[cover_idx], cover_idx)]

    order = list(range(len(_INTERIORS)))
    rng.shuffle(order)
    interior_picks = []
    while len(interior_picks) < count - 1:
        interior_picks.extend(order)
    for k in interior_picks[: count - 1]:
        chosen.append((*_INTERIORS[k], 100 + k))  # stable per-entry lock keeps the pool bounded

    photos = []
    for caption, tags, lock in chosen:
        url = f"https://loremflickr.com/800/600/{tags}?lock={lock}"
        data = _cached_bytes(url, fallback_seed=f"re-{lock}", rng=rng)
        photos.append((ContentFile(data, name=f"{tags.split(',')[0]}-{lock}.jpg"), caption))
    return photos


def fetch_mock_image(seed, *, rng, width=800, height=600):
    """Return a ``ContentFile`` holding a deterministic random stock photo for ``seed``.

    Uses Picsum's seeded endpoint; any network/IO error falls back to a solid-colour placeholder
    PNG. Kept for non-listing mock imagery and as the documented fallback source.
    """
    url = f"https://picsum.photos/seed/{seed}/{width}/{height}"
    try:
        return ContentFile(_download(url), name=f"{seed}.jpg")
    except Exception:  # noqa: BLE001 — any network/IO error falls back to a placeholder
        return ContentFile(_placeholder_bytes(rng), name=f"{seed}.png")
