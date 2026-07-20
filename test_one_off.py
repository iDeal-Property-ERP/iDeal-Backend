import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
django.setup()

from property.models import Property, District, OneOffDeal
from decimal import Decimal
from django.test import Client

d = District.objects.create(name="Dist1", city="City")
p = Property.objects.create(name="Prop", district=d, engagement_type="one_off", ask_price=Decimal("100"))
deal = OneOffDeal.objects.create(property=p, seller_name="Seller", seller_phone="123")

client = Client()
# We need to authenticate. 
from tests.factories import UserFactory
from tests.integration.property.test_api import _make_jwt
user = UserFactory(role="management")
auth = _make_jwt(user)

resp = client.patch(f"/api/v1/properties/{p.id}/one-off/", {"ask_price": 500}, content_type="application/json", **auth)
print(resp.status_code, resp.json())
p.refresh_from_db()
print("DB ask_price:", p.ask_price)

