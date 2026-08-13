from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from property.models import PropertyPhoto

from tests.factories import PropertyFactory


def _uploaded_image(name, *, size=(1600, 800), color="red"):
    content = BytesIO()
    Image.new("RGB", size, color=color).save(content, format="PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


def _uploaded_exif_oriented_image(name):
    content = BytesIO()
    image = Image.new("RGB", (400, 100), color="green")
    exif = Image.Exif()
    exif[274] = 6
    image.save(content, format="JPEG", exif=exif)
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/jpeg")


@pytest.mark.django_db
class TestPropertyPhotoVariants:
    def test_new_original_creates_webp_variants_without_changing_original(self):
        photo = PropertyPhoto.objects.create(property=PropertyFactory(), image=_uploaded_image("original.png"))
        original_name = photo.image.name
        photo.refresh_from_db()

        assert photo.image.name == original_name
        assert photo.preview_image.name.endswith("-preview.webp")
        assert photo.display_image.name.endswith("-display.webp")
        with Image.open(photo.preview_image) as preview:
            assert preview.format == "WEBP"
            assert preview.width == 64
        with Image.open(photo.display_image) as display:
            assert display.format == "WEBP"
            assert display.width == 1280

    def test_replacing_original_regenerates_variants(self):
        photo = PropertyPhoto.objects.create(property=PropertyFactory(), image=_uploaded_image("first.png"))
        old_original = photo.image.name
        old_preview = photo.preview_image.name
        old_display = photo.display_image.name

        photo.image = _uploaded_image("replacement.png", size=(320, 160), color="blue")
        photo.save(update_fields=["image", "updated_at"])
        photo.refresh_from_db()

        assert photo.image.name != old_original
        assert photo.preview_image.name != old_preview
        assert photo.display_image.name != old_display
        assert not photo.image.storage.exists(old_preview)
        assert not photo.image.storage.exists(old_display)
        with Image.open(photo.preview_image) as preview:
            assert preview.width == 64
        with Image.open(photo.display_image) as display:
            assert display.width == 320

    def test_variants_transpose_exif_and_never_upscale(self):
        photo = PropertyPhoto.objects.create(
            property=PropertyFactory(),
            image=_uploaded_exif_oriented_image("rotated.jpg"),
        )
        photo.refresh_from_db()

        with Image.open(photo.preview_image) as preview:
            assert preview.size == (64, 256)
        with Image.open(photo.display_image) as display:
            assert display.size == (100, 400)

        small = PropertyPhoto.objects.create(
            property=PropertyFactory(),
            image=_uploaded_image("small.png", size=(32, 16)),
        )
        small.refresh_from_db()
        with Image.open(small.preview_image) as preview:
            assert preview.size == (32, 16)
        with Image.open(small.display_image) as display:
            assert display.size == (32, 16)

    def test_legacy_path_row_does_not_generate_variants(self):
        with patch.object(PropertyPhoto, "_generate_variants") as generate_variants:
            photo = PropertyPhoto.objects.create(
                property=PropertyFactory(),
                image="properties/photos/legacy.jpg",
            )

        generate_variants.assert_not_called()
        photo.refresh_from_db()
        assert not photo.preview_image.name
        assert not photo.display_image.name

    def test_metadata_only_save_does_not_regenerate_variants(self):
        photo = PropertyPhoto.objects.create(property=PropertyFactory(), image=_uploaded_image("original.png"))
        original = photo.image.name
        preview = photo.preview_image.name
        display = photo.display_image.name

        with patch.object(PropertyPhoto, "_generate_variants") as generate_variants:
            photo.caption = "Updated caption"
            photo.save(update_fields=["caption", "updated_at"])

        photo.refresh_from_db()
        generate_variants.assert_not_called()
        assert photo.image.name == original
        assert photo.preview_image.name == preview
        assert photo.display_image.name == display

    def test_generation_failure_keeps_original_and_clears_variants(self):
        with patch.object(PropertyPhoto, "_variant_contents", side_effect=OSError("Pillow unavailable")):
            photo = PropertyPhoto.objects.create(property=PropertyFactory(), image=_uploaded_image("original.png"))

        photo.refresh_from_db()
        assert photo.image.name.startswith("properties/photos/original")
        assert photo.image.name.endswith(".png")
        assert photo.image.storage.exists(photo.image.name)
        assert photo.preview_image.name is None
        assert photo.display_image.name is None
