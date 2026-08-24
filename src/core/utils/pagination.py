from django.core.paginator import Paginator

from core.api.schemas import Pagination, PaginationPage


def build_paginated_response(items: list, page: int, per_page: int) -> Pagination:
    paginator = Paginator(items, per_page)
    django_page = paginator.get_page(page)
    return Pagination(
        count=paginator.count,
        num_pages=paginator.num_pages,
        per_page=paginator.per_page,
        page=PaginationPage(
            number=django_page.number,
            object_list=list(django_page.object_list),
        ),
    )


def build_paginated_response_from_queryset(
    qs, page: int, per_page: int, serialize, *, serialize_page=None
) -> Pagination:
    """Slice the queryset before converting rows to output models."""
    paginator = Paginator(qs, per_page)
    django_page = paginator.get_page(page)
    objects = list(django_page.object_list)
    serialized = serialize_page(objects) if serialize_page is not None else [serialize(obj) for obj in objects]
    return Pagination(
        count=paginator.count,
        num_pages=paginator.num_pages,
        per_page=paginator.per_page,
        page=PaginationPage(
            number=django_page.number,
            object_list=serialized,
        ),
    )
