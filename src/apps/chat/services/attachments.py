from core.utils.uploads import validate_image

CHAT_MAX_IMAGE_BYTES = 5 * 1024 * 1024
CHAT_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}


def validate_chat_image(uploaded_file):
    validate_image(
        uploaded_file,
        max_bytes=CHAT_MAX_IMAGE_BYTES,
        allowed_extensions=CHAT_ALLOWED_EXTENSIONS,
    )
