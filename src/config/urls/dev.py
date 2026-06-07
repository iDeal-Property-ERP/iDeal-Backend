from django.conf import settings
from django.urls import path

if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls
    from dmr.openapi import build_schema
    from dmr.openapi.views import OpenAPIJsonView, RedocView, SwaggerView
    from dmr.routing import Router

    from api.url_router import urlpatterns as api_urlpatterns

    router = Router("api/", api_urlpatterns)
    schema = build_schema(router)

    urlpatterns = [
        *debug_toolbar_urls(),
        path("docs/schema.json", OpenAPIJsonView.as_view(schema=schema), name="openapi-json"),
        path("docs/swagger/", SwaggerView.as_view(schema=schema), name="swagger"),
        path("docs/redoc/", RedocView.as_view(schema=schema), name="redoc"),
    ]
