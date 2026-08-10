import pytest
from chat.services.attachments import validate_chat_image
from django.core.files.uploadedfile import SimpleUploadedFile

from core.utils.uploads import MAX_IMAGE_BYTES, UploadError, validate_image


def uploaded_file(*, size, name="photo.png", content_type="image/png"):
    return SimpleUploadedFile(name, b"x" * size, content_type=content_type)


def test_chat_limit_rejects_one_byte_over_five_megabytes():
    with pytest.raises(UploadError, match="5 MB"):
        validate_image(uploaded_file(size=5 * 1024 * 1024 + 1), max_bytes=5 * 1024 * 1024)


def test_chat_limit_accepts_exactly_five_megabytes():
    validate_image(uploaded_file(size=5 * 1024 * 1024), max_bytes=5 * 1024 * 1024)


def test_default_ten_megabyte_limit_remains_unchanged():
    validate_image(uploaded_file(size=MAX_IMAGE_BYTES))
    with pytest.raises(UploadError, match="10 MB"):
        validate_image(uploaded_file(size=MAX_IMAGE_BYTES + 1))


def test_disallowed_content_type_is_rejected():
    with pytest.raises(UploadError, match="application/pdf"):
        validate_image(uploaded_file(size=1, name="photo.png", content_type="application/pdf"))


def test_extension_cross_check_rejects_pdf_even_with_image_content_type():
    with pytest.raises(UploadError, match=r"\.pdf"):
        validate_image(
            uploaded_file(size=1, name="photo.pdf", content_type="image/png"),
            max_bytes=5 * 1024 * 1024,
            allowed_extensions={"png", "jpg", "jpeg", "webp", "gif"},
        )


def test_chat_image_validator_reuses_mime_allowlist_and_extension_allowlist():
    validate_chat_image(uploaded_file(size=1, name="photo.WEBP", content_type="image/webp"))
