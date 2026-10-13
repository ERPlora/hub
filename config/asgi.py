"""ASGI entry point of hub-next: the ``application`` that Daphne serves.

``ignore_root_path`` wraps it because Daphne trusts its client's own ``Daphne-Root-Path`` header:
it copies it into ``scope["root_path"]``, which Django takes as the script prefix, stripped from the
path it resolves and put in front of every URL it builds. The project is served at the root of its
host, so that prefix is always empty and a request is answered for its real path (ERPlora/hub#2).

https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application
from live.asgi import ignore_root_path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = ignore_root_path(get_asgi_application())
