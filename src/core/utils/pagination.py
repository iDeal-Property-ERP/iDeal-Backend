from django.core.paginator import Paginator
from dmr.pagination import Page, Paginated


def build_paginated_response(items: list, page: int, per_page: int) -> Paginated:
    paginator = Paginator(items, per_page)
    django_page = paginator.get_page(page)
    return Paginated(
        count=paginator.count,
        num_pages=paginator.num_pages,
        per_page=paginator.per_page,
        page=Page(
            number=django_page.number,
            object_list=list(django_page.object_list),
        ),
    )


def build_paginated_response_from_queryset(qs, page: int, per_page: int, serialize) -> Paginated:
    paginator = Paginator(qs, per_page)
    django_page = paginator.get_page(page)
    return Paginated(
        count=paginator.count,
        num_pages=paginator.num_pages,
        per_page=paginator.per_page,
        page=Page(
            number=django_page.number,
            object_list=[serialize(obj) for obj in django_page.object_list],
        ),
    )
