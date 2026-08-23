import os
import sys

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

sys.path.append(os.path.join(os.path.dirname(__file__), "../../apps"))  # noqa

from chat.routing import websocket_urlpatterns
from chat.ws_auth import WebSocketJWTAuthMiddleware

application = ProtocolTypeRouter(
    {
        "http": get_asgi_application(),
        "websocket": AllowedHostsOriginValidator(WebSocketJWTAuthMiddleware(URLRouter(websocket_urlpatterns))),
    }
)
