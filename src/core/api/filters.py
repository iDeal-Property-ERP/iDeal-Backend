"""Query-model-first adapters for django-filter.

DMR/Pydantic owns parsing and validation.  ``django_filters.FilterSet`` then
owns the queryset transformations.  This keeps malformed known parameters out
of application code while preserving v1's policy of ignoring unknown keys.
"""

from __future__ import annotations

import pydantic
from django.db.models import QuerySet
from django_filters import FilterSet


class PydanticFilterSet[QueryT: pydantic.BaseModel](FilterSet):
    """A FilterSet constructed from an already-validated query model."""

    def __init__(self, *, query: QueryT, request, queryset: QuerySet):
        # ``data=None`` prevents django-filter from reparsing the request.  The
        # Pydantic model is the single parsing boundary for a v1 endpoint.
        super().__init__(data=None, queryset=queryset, request=request)
        self.query = query

    def apply(self) -> QuerySet:
        """Apply only search/filter/order transformations to the base queryset."""
        return self.filter_queryset(self.queryset)
