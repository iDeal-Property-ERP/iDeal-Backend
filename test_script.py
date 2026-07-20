import os, sys
sys.path.append("/home/mehroj/Claude/Projects/iDeal/Backend/src")
sys.path.append("/home/mehroj/Claude/Projects/iDeal/Backend/src/apps")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')

import django
django.setup()

from property.models import Property, District, OneOffDeal
from marketplace.models import Listing
from decimal import Decimal
import json
from django.core.management import call_command
from api.v1.property.schemas import OneOffPropertyUpdateInput

call_command('flush', '--noinput')

d = District.objects.create(name="Dist1", city="City")
p = Property.objects.create(name="Prop", district=d, engagement_type="one_off", ask_price=Decimal("100"), description="old", status="vacant")
deal = OneOffDeal.objects.create(property=p, seller_name="Seller", seller_phone="123", status="active")
l = Listing.objects.create(property=p, status="published", is_active=True, monthly_price=Decimal("100"), description="old")

payload = {"ask_price": "600", "description": "new"}
parsed = OneOffPropertyUpdateInput.model_validate(payload)
data = parsed.model_dump(exclude_unset=True)
brokerage = data.pop("brokerage", None)

from api.v1.property.views import _apply_one_off_property_data
_apply_one_off_property_data(p, data)
p.save()

l.refresh_from_db()
print("Listing price:", l.monthly_price)
print("Listing description:", l.description)
