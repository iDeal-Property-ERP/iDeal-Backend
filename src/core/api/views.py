from http import HTTPStatus
from typing import Any

import pydantic
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from dmr import Body, Controller, Path, Query
from dmr.plugins.pydantic import PydanticFastSerializer
from dmr.response import APIError

from core.api.permissions import BlacklistAwareJWTSyncAuth
from core.models import BaseModel
from core.utils.pagination import build_paginated_response


class BaseController(Controller[PydanticFastSerializer]):
    SUCCESS_MESSAGE = _("OK")
    ERROR_MESSAGE = _("NOT OK")
    auth = (BlacklistAwareJWTSyncAuth(),)

    @staticmethod
    def ok(data, *, status_code=None):
        raw_data = {
            "success": True,
            "message": str(_("OK")),
            "data": data,
        }
        if status_code is not None:
            return JsonResponse(raw_data, status=status_code)
        return raw_data

    @staticmethod
    def fail(error, message=None, status_code=HTTPStatus.BAD_REQUEST):
        if message is None:
            message = str(_("NOT OK"))
        raise APIError(
            raw_data={
                "success": False,
                "message": message,
                "error": error,
            },
            status_code=status_code,
        )


class ListQuery(pydantic.BaseModel):
    page: int | None = None
    per_page: int = 20


class DetailPath(pydantic.BaseModel):
    pk: int


class GenericController(BaseController):
    model: type[BaseModel] | None = None
    output_schema: type[pydantic.BaseModel] | None = None
    create_schema: type[pydantic.BaseModel] | None = None
    update_schema: type[pydantic.BaseModel] | None = None

    def _get_model(self) -> type[BaseModel]:
        if self.model is None:
            raise NotImplementedError(
                f"{type(self).__name__} must set `model` attribute",
            )
        return self.model

    def get_queryset(self):
        return self._get_model().objects.all()

    def get_object(self, **lookup_kwargs):
        return get_object_or_404(self.get_queryset(), **lookup_kwargs)

    def to_output(self, instance):
        if self.output_schema is not None:
            return self.output_schema.model_validate(instance).model_dump(mode="json")
        return instance

    def perform_create(self, validated_data: dict[str, Any]):
        return self._get_model().objects.create(**validated_data)

    def perform_update(self, instance, validated_data: dict[str, Any]):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance

    def perform_destroy(self, instance):
        instance.delete()

    def list_response(self, qs, parsed_query) -> dict:
        items = [self.to_output(obj) for obj in qs]
        if parsed_query.page is not None:
            paginated = build_paginated_response(items, parsed_query.page, parsed_query.per_page)
            return self.ok(paginated)
        return self.ok(items)

    def _validate_body(self, schema_cls, data, *, exclude_unset=False):
        try:
            validated = schema_cls.model_validate(data)
        except pydantic.ValidationError as err:
            raw_errors = err.errors(include_url=False)
            for e in raw_errors:
                e.pop("ctx", None)
            self.fail(error=raw_errors, message=str(_("Validation error")))
        return validated.model_dump(exclude_unset=exclude_unset) if exclude_unset else validated.model_dump()


class CreateAPIView(GenericController):
    def post(self, parsed_body: Body[dict]) -> dict:
        data = self._validate_body(self.create_schema, parsed_body) if self.create_schema is not None else parsed_body
        instance = self.perform_create(data)
        return self.ok(self.to_output(instance))


class ListAPIView(GenericController):
    def get(self, parsed_query: Query[ListQuery]) -> dict:
        qs = self.get_queryset()
        items = [self.to_output(obj) for obj in qs]
        if parsed_query.page is not None:
            paginated = build_paginated_response(
                items,
                parsed_query.page,
                parsed_query.per_page,
            )
            return self.ok(paginated)
        return self.ok(items)


class RetrieveAPIView(GenericController):
    def get(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        return self.ok(self.to_output(instance))


class UpdateAPIView(GenericController):
    def put(self, parsed_path: Path[DetailPath], parsed_body: Body[dict]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        data = self._validate_body(self.update_schema, parsed_body) if self.update_schema is not None else parsed_body
        instance = self.perform_update(instance, data)
        return self.ok(self.to_output(instance))


class PartialUpdateAPIView(GenericController):
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[dict]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        if self.update_schema is not None:
            data = self._validate_body(self.update_schema, parsed_body, exclude_unset=True)
        else:
            data = parsed_body
        instance = self.perform_update(instance, data)
        return self.ok(self.to_output(instance))


class DeleteAPIView(GenericController):
    def delete(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        self.perform_destroy(instance)
        return self.ok({"deleted": True})
