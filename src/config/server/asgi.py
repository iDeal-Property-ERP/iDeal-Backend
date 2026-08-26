import os
import sys

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

sys.path.append(os.path.join(os.path.dirname(__file__), "../../apps"))  # noqa

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402
from chat.routing import websocket_urlpatterns  # noqa: E402
from chat.ws_auth import WebSocketJWTAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(WebSocketJWTAuthMiddleware(URLRouter(websocket_urlpatterns))),  # noqa
    }
)
