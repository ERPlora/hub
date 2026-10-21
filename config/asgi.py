"""ASGI entry point of hub-next: the ``application`` that Daphne serves.

``ignore_root_path`` wraps it because Daphne trusts its client's own ``Daphne-Root-Path`` header:
it copies it into ``scope["root_path"]``, which Django takes as the script prefix, stripped from the
path it resolves and put in front of every URL it builds. The project is served at the root of its
host, so that prefix is always empty and a request is answered for its real path (ERPlora/hub#2).

HTTP goes to Django. Django serves no WebSocket, and the Hub has exactly one, ``/ws/print`` (the print
host's channel, PLAN-HUB §5): a plain ASGI application of ``base.ws_print``, without Channels (round 11:
no channel layer, no ``channels`` installed). Any other WebSocket path is refused at the handshake
(close 4404 before the accept: Daphne answers it 403).

https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from live.asgi import ignore_root_path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_application = get_asgi_application()

# After Django is set up: the channel imports the registry's models.
from base.ws_print import PATH as PRINT_PATH, print_socket  # noqa: E402

#: The Hub's WebSockets, by path.
WEBSOCKETS = {PRINT_PATH: print_socket}
#: Close code of a WebSocket path that does not exist.
NO_SUCH_WEBSOCKET = 4404


async def route(scope, receive, send):
    """WebSockets by path; everything else to Django, as before."""
    if scope["type"] != "websocket":
        return await django_application(scope, receive, send)
    consumer = WEBSOCKETS.get(scope["path"])
    if consumer is None:
        await receive()  # websocket.connect
        await send({"type": "websocket.close", "code": NO_SUCH_WEBSOCKET})
        return None
    return await consumer(scope, receive, send)


application = ignore_root_path(route)
