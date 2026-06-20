"""Reusable multipart image-upload helper for DMR controllers.

DMR controllers parse JSON bodies via Pydantic. For file uploads the controller
method skips the ``Body[...]`` parameter and reads ``self.request.FILES``
directly, then delegates here. Reuse this for any future photo-upload endpoint
(PropertyPhoto, ServiceRequestPhoto, etc.).
"""

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


class UploadError(ValueError):
    """Raised when an uploaded file fails validation."""


def validate_image(uploaded_file):
    if uploaded_file.size > MAX_IMAGE_BYTES:
        raise UploadError(f"File '{uploaded_file.name}' exceeds the 10 MB limit")
    content_type = getattr(uploaded_file, "content_type", None)
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise UploadError(f"Unsupported image type '{content_type}'")


def save_uploaded_images(model, fk_field, fk_value, files, *, image_field="image", extra=None):
    """Validate and persist ``files`` as ``model`` rows linked via ``fk_field``.

    Returns the list of created instances. Raises :class:`UploadError` on the
    first invalid file (callers should translate this into an API failure).
    """
    extra = extra or {}
    created = []
    for uploaded in files:
        validate_image(uploaded)
        instance = model.objects.create(**{fk_field: fk_value, image_field: uploaded, **extra})
        created.append(instance)
    return created
