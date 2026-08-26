from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from account.models import User
from contract.models import Lease
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone
from inventory.models import InventoryAct, InventoryActItem, InventoryActPhoto
from PIL import Image
from property.models import Property

from core.constants import ConditionRating, InventoryActStatus, InventoryActType

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_FORMAT_MAPPING = {
    "JPEG": ("image/jpeg", (".jpg", ".jpeg")),
    "PNG": ("image/png", (".png",)),
    "WEBP": ("image/webp", (".webp",)),
}


class InventorySubmissionError(ValueError):
    """Raised when inventory submission data or files fail validation."""


def validate_inventory_image(file: UploadedFile) -> str:
    if file.size > MAX_IMAGE_BYTES:
        raise InventorySubmissionError(f"Image '{file.name}' exceeds the 10 MB limit.")

    try:
        content = file.read()
        file.seek(0)
        img = Image.open(BytesIO(content))
        img.verify()
    except Exception as err:
        raise InventorySubmissionError(f"Image '{file.name}' is corrupt or cannot be decoded.") from err

    fmt = (img.format or "").upper()
    if fmt not in ALLOWED_FORMAT_MAPPING:
        raise InventorySubmissionError(f"Image '{file.name}' format '{fmt}' is not supported. Use JPEG, PNG, or WebP.")

    expected_mime, valid_exts = ALLOWED_FORMAT_MAPPING[fmt]
    content_type = getattr(file, "content_type", None)
    if content_type and content_type.lower() != expected_mime:
        raise InventorySubmissionError(
            f"Image '{file.name}' MIME type '{content_type}' does not match actual image format '{fmt}'."
        )

    file_name = file.name or ""
    ext = ("." + file_name.rsplit(".", 1)[-1].lower()) if "." in file_name else ""
    if ext not in valid_exts:
        raise InventorySubmissionError(
            f"Image '{file.name}' extension '{ext}' does not match actual image format '{fmt}'."
        )

    return fmt


class InventorySubmissionService:
    @staticmethod
    def submit_act(
        *,
        user: User,
        data: dict[str, Any],
        files: list[UploadedFile],
    ) -> InventoryAct:
        property_id = data.get("property_id")
        prop = Property.objects.filter(pk=property_id, deleted_at__isnull=True).first()
        if not prop:
            raise InventorySubmissionError("Property not found.")

        lease_id = data.get("lease_id")
        lease = None
        if lease_id:
            lease = Lease.objects.filter(pk=lease_id, deleted_at__isnull=True).first()
            if not lease:
                raise InventorySubmissionError("Lease not found.")
            if lease.property_id != prop.id:
                raise InventorySubmissionError("Lease does not belong to the selected property.")

        items_data = data.get("items") or []
        if not items_data:
            raise InventorySubmissionError("An inventory act requires at least one item.")

        valid_conditions = set(ConditionRating.values())
        for idx, item in enumerate(items_data):
            area = (item.get("area") or "").strip()
            if not area:
                raise InventorySubmissionError(f"Item #{idx + 1} must have a non-empty area name.")
            cond = item.get("condition", ConditionRating.GOOD)
            if cond not in valid_conditions:
                raise InventorySubmissionError(f"Item #{idx + 1} has invalid condition '{cond}'.")

        for f in files:
            validate_inventory_image(f)

        act_type = data.get("act_type", InventoryActType.GENERAL)
        if act_type not in InventoryActType.values():
            act_type = InventoryActType.GENERAL

        ack_name = data.get("acknowledged_by_name")
        ack_note = data.get("acknowledgment_note")
        now = timezone.now()

        created_photos: list[InventoryActPhoto] = []

        try:
            with transaction.atomic():
                act = InventoryAct.objects.create(
                    property=prop,
                    lease=lease,
                    act_type=act_type,
                    status=InventoryActStatus.FINALIZED,
                    created_by=user,
                    notes=data.get("notes", ""),
                    finalized_at=now,
                    acknowledged_by_name=ack_name or None,
                    acknowledged_at=now if ack_name else None,
                    acknowledgment_note=ack_note or None,
                )

                item_objects: list[InventoryActItem] = []
                for idx, item_dict in enumerate(items_data):
                    item_obj = InventoryActItem.objects.create(
                        act=act,
                        area=(item_dict.get("area") or "").strip(),
                        condition=item_dict.get("condition", ConditionRating.GOOD),
                        notes=item_dict.get("notes") or "",
                        sort_order=item_dict.get("sort_order", idx),
                    )
                    item_objects.append(item_obj)

                # Assign photos
                # photo_item_mapping: map from file index to item index if provided
                photo_item_map = data.get("photo_item_map") or {}
                captions = data.get("captions") or []
                for idx, file_obj in enumerate(files):
                    item_for_photo = None
                    str_idx = str(idx)
                    if str_idx in photo_item_map:
                        mapped_item_idx = photo_item_map[str_idx]
                        if 0 <= mapped_item_idx < len(item_objects):
                            item_for_photo = item_objects[mapped_item_idx]

                    caption = captions[idx] if idx < len(captions) else None
                    photo = InventoryActPhoto.objects.create(
                        act=act,
                        item=item_for_photo,
                        image=file_obj,
                        caption=caption or None,
                    )
                    created_photos.append(photo)

        except Exception as err:
            for photo in created_photos:
                try:
                    if photo.image:
                        photo.image.delete(save=False)
                except Exception:
                    pass
            raise err

        return act
