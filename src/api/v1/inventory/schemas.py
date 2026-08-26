from __future__ import annotations

from datetime import datetime

import pydantic

from core.constants import ConditionRating, InventoryActType


class InventoryActPhotoOutput(pydantic.BaseModel):
    id: int
    item_id: int | None
    image_url: str | None
    caption: str | None
    created_at: datetime

    model_config = pydantic.ConfigDict(from_attributes=True)

    @pydantic.model_validator(mode="before")
    @classmethod
    def extract(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "item_id": v.item_id,
            "image_url": v.image.url if v.image else None,
            "caption": v.caption,
            "created_at": v.created_at,
        }


class InventoryActItemOutput(pydantic.BaseModel):
    id: int
    area: str
    condition: str
    notes: str | None
    sort_order: int

    model_config = pydantic.ConfigDict(from_attributes=True)


class InventoryActOutput(pydantic.BaseModel):
    id: int
    property_id: int
    property_name: str
    lease_id: int | None
    act_type: str
    status: str
    created_by_id: int
    notes: str | None
    finalized_at: datetime | None
    acknowledged_by_name: str | None
    acknowledged_at: datetime | None
    items: list[InventoryActItemOutput]
    photos: list[InventoryActPhotoOutput]
    created_at: datetime
    updated_at: datetime

    @pydantic.model_validator(mode="before")
    @classmethod
    def extract(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "property_id": v.property_id,
            "property_name": v.property.name,
            "lease_id": v.lease_id,
            "act_type": v.act_type,
            "status": v.status,
            "created_by_id": v.created_by_id,
            "notes": v.notes,
            "finalized_at": v.finalized_at,
            "acknowledged_by_name": v.acknowledged_by_name,
            "acknowledged_at": v.acknowledged_at,
            "items": list(v.items.all()),
            "photos": list(v.photos.all()),
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class InventoryActListOutput(pydantic.BaseModel):
    id: int
    property_id: int
    property_name: str
    lease_id: int | None
    act_type: str
    status: str
    acknowledged_by_name: str | None
    acknowledged_at: datetime | None
    item_count: int
    photo_count: int
    created_at: datetime
    updated_at: datetime

    @pydantic.model_validator(mode="before")
    @classmethod
    def extract(cls, v):
        if isinstance(v, dict):
            return v
        return {
            "id": v.id,
            "property_id": v.property_id,
            "property_name": v.property.name,
            "lease_id": v.lease_id,
            "act_type": v.act_type,
            "status": v.status,
            "acknowledged_by_name": v.acknowledged_by_name,
            "acknowledged_at": v.acknowledged_at,
            "item_count": v.items.count(),
            "photo_count": v.photos.count(),
            "created_at": v.created_at,
            "updated_at": v.updated_at,
        }


class InventoryActItemInput(pydantic.BaseModel):
    area: str
    condition: str = ConditionRating.GOOD
    notes: str | None = None
    sort_order: int = 0


class InventoryActSubmitPayload(pydantic.BaseModel):
    property_id: int
    lease_id: int | None = None
    act_type: str = InventoryActType.GENERAL
    notes: str | None = None
    items: list[InventoryActItemInput] = pydantic.Field(min_length=1)
    photo_item_map: dict[str, int] = pydantic.Field(default_factory=dict)
    captions: list[str] = pydantic.Field(default_factory=list)
    acknowledged_by_name: str | None = None
    acknowledgment_note: str | None = None


class InventoryActAcknowledgeInput(pydantic.BaseModel):
    acknowledged_by_name: str
    acknowledgment_note: str | None = None
