import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
django.setup()

from property.models import Property, District, OneOffDeal
from api.v1.property.schemas import OneOffPropertyUpdateInput
from decimal import Decimal

# Create a district
d, _ = District.objects.get_or_create(name="Test District", city="Test City")

# Create a one-off property
prop = Property.objects.create(
    name="Test One Off",
    district=d,
    engagement_type="one_off",
    status="vacant",
    ask_price=Decimal("500.00")
)
deal = OneOffDeal.objects.create(
    property=prop,
    seller_name="Seller",
    seller_phone="123",
    status="active"
)

# Simulate what OneOffPropertyUpdateView does
data = {"ask_price": Decimal("600.00")}
from api.v1.property.views import _apply_one_off_property_data
_apply_one_off_property_data(prop, data)
prop.save()

prop.refresh_from_db()
print("After update ask_price:", prop.ask_price)
