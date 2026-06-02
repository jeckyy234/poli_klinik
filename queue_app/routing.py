from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/antrian/(?P<poli_kode>\w+)/$', consumers.AntrianConsumer.as_asgi()),
]
