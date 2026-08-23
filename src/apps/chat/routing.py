from chat.consumers import ChatConsumer
from django.urls import path

websocket_urlpatterns = [
    path("ws/v1/chat/", ChatConsumer.as_asgi()),
]
