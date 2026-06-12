from django.contrib import admin
from marketplace.models import Listing, ViewingRequest

from core.admin import BaseSoftDeleteModelAdmin


@admin.register(Listing)
class ListingAdmin(BaseSoftDeleteModelAdmin):
    pass


@admin.register(ViewingRequest)
class ViewingRequestAdmin(BaseSoftDeleteModelAdmin):
    pass
