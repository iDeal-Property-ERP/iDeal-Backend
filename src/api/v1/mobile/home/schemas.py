import pydantic


class MobileHomeFeedQuery(pydantic.BaseModel):
    page: int = 1
    per_page: int = 20
    q: str | None = None
    district_id: int | None = None
    price_min: float | None = None
    price_max: float | None = None
    rooms_min: int | None = None
    rooms_max: int | None = None
    verified: bool | None = None
    furnishing: str | None = None
    tariff: str | None = None


class MobileListingCard(pydantic.BaseModel):
    id: int
    property_id: int
    title: str
    district: str | None
    address: str
    property_type: str
    rooms: int | None
    area_sqm: int | None
    floor: int | None
    total_floors: int | None
    furnishing: str
    price: float | None
    currency: str
    tariff: str
    is_verified: bool
    is_featured: bool
    score: float
    review_count: int
    cover_image_url: str | None
    map_lat: float | None
    map_lon: float | None
