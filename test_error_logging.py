import os, sys
sys.path.append("/home/mehroj/Claude/Projects/iDeal/Backend/src")
sys.path.append("/home/mehroj/Claude/Projects/iDeal/Backend/src/apps")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')

import django
django.setup()

from django.test import RequestFactory
from core.api.exceptions import global_error_handler
import logging

class DummyController:
    def __init__(self, request):
        self.request = request

rf = RequestFactory()
request = rf.get('/dummy/')
controller = DummyController(request)

try:
    1 / 0
except Exception as e:
    exc = e

print("Simulating error handler...")
global_error_handler(None, controller, exc)
print("Done!")
