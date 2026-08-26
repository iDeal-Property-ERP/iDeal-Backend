from __future__ import annotations

import pydantic


class MobileMyListingsStatsOutput(pydantic.BaseModel):
    total_count: int = 0
    approved_count: int = 0
    pending_count: int = 0
    rented_count: int = 0
    rejected_count: int = 0
    archived_count: int = 0


class MobileMyListingItemOutput(pydantic.BaseModel):
    id: int | None = None
    property_id: int
    title: str
    address: str | None = None
    district: str | None = None
    price: float | None = None
    currency: str = "USD"
    status: str
    status_display: str
    cover_image_url: str | None = None
    cover_preview_url: str | None = None
    cover_display_url: str | None = None
    views_count: int = 0
    rooms: int | None = None
    area_sqm: int | None = None
    rejection_reason: str | None = None
    created_at: str | None = None


class MobileMyListingsResponse(pydantic.BaseModel):
    stats: MobileMyListingsStatsOutput
    listings: list[MobileMyListingItemOutput]


class MobileMyListingsQuery(pydantic.BaseModel):
    status: str = "all"
