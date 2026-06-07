import os
import sys

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

sys.path.append(os.path.join(os.path.dirname(__file__), "../../apps"))  # noqa

application = get_wsgi_application()
