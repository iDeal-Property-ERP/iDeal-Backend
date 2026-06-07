from typing import Any

import pydantic
from django.shortcuts import get_object_or_404
from dmr import Body, Controller, Path, Query
from dmr.plugins.pydantic import PydanticFastSerializer
from dmr.security.jwt.auth import JWTSyncAuth

from core.models import BaseModel
from core.utils.pagination import build_paginated_response


class BaseController(Controller[PydanticFastSerializer]):
    SUCCESS_MESSAGE = "OK"
    ERROR_MESSAGE = "NOT OK"
    auth = (JWTSyncAuth(),)

    @staticmethod
    def ok(data):
        return {
            "success": True,
            "message": "OK",
            "data": data,
        }

    @staticmethod
    def fail(error, message: str = "NOT OK"):
        return {
            "success": False,
            "message": message,
            "error": error,
        }


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


class CreateAPIView(GenericController):
    def post(self, parsed_body: Body[dict]) -> dict:
        if self.create_schema is not None:
            validated = self.create_schema.model_validate(parsed_body)
            data = validated.model_dump()
        else:
            data = parsed_body
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
        if self.update_schema is not None:
            validated = self.update_schema.model_validate(parsed_body)
            data = validated.model_dump()
        else:
            data = parsed_body
        instance = self.perform_update(instance, data)
        return self.ok(self.to_output(instance))


class PartialUpdateAPIView(GenericController):
    def patch(self, parsed_path: Path[DetailPath], parsed_body: Body[dict]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        if self.update_schema is not None:
            validated = self.update_schema.model_validate(parsed_body)
            data = validated.model_dump(exclude_unset=True)
        else:
            data = parsed_body
        instance = self.perform_update(instance, data)
        return self.ok(self.to_output(instance))


class DeleteAPIView(GenericController):
    def delete(self, parsed_path: Path[DetailPath]) -> dict:
        instance = self.get_object(pk=parsed_path.pk)
        self.perform_destroy(instance)
        return self.ok({"deleted": True})
