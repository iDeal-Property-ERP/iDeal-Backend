from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.url_router"), name="url_router"),
    path("api/v1/payment-webhooks/", include("api.v1.payment_providers.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    from config.urls import dev

    urlpatterns += dev.urlpatterns
