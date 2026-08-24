"""Small, explicit service construction primitives for controllers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class ServiceFactory:
    """Per-request service factory with a narrow, overridable seam for tests."""

    def build(self, service_type: type, **dependencies: Any) -> Any:
        return service_type(**dependencies)


class ServiceControllerMixin:
    """Lets controllers create stateful services without static service globals."""

    service_factory_class = ServiceFactory
    service_dependencies: dict[str, dict[str, Any] | Callable[[Any], dict[str, Any]]] = {}

    def get_service_factory(self) -> ServiceFactory:
        return self.service_factory_class()

    def get_service(self, service_type: type, *, name: str | None = None) -> Any:
        key = name or service_type.__name__
        cache = getattr(self, "_services", None)
        if cache is None:
            cache = self._services = {}
        if key not in cache:
            configured = self.service_dependencies.get(key, {})
            dependencies = configured(self) if callable(configured) else configured
            cache[key] = self.get_service_factory().build(service_type, **dependencies)
        return cache[key]
