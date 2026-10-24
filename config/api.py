"""The hub's API (django-ninja), mounted at ``/api/``: the SPA's and the integrations'.

Every route calls one operation (``ensure_api_parity`` keeps it so) and every failure answers with
the single envelope ``{"error": {...}}``. Authentication is Django's session, which ninja checks
together with the CSRF token on every unsafe method (the SDK sends ``X-CSRFToken``); a route open
to anonymous visitors says ``auth=None``. The business's API keys (``erpk_live``, ``base.api_keys``) open the
routes of the published operations, before the session.
"""

from django.conf import settings
from base import api_keys
from live.ninja import install_error_handlers, mount_app_routers
from ninja import NinjaAPI
from ninja.openapi.docs import Swagger
from ninja.security import django_auth


class NonceSwagger(Swagger):
    """Swagger UI from ninja's own static files, its scripts carrying the response's CSP nonce."""

    template = "base/swagger.html"


def build_api(*, urls_namespace: str = "api", docs: bool | None = None) -> NinjaAPI:
    """A NinjaAPI configured as the hub's: session auth with CSRF, error envelope, docs in DEBUG.

    Swagger only with DEBUG (by default): production enforces Trusted Types, which Swagger UI
    does not support.
    """
    with_docs = settings.DEBUG if docs is None else docs
    api = NinjaAPI(
        title="ERPlora Hub API",
        version="1",
        openapi_url="/openapi.json",
        docs=NonceSwagger(),
        docs_url="/docs" if with_docs else None,
        auth=django_auth,
        urls_namespace=urls_namespace,
    )
    install_error_handlers(api)
    return api


api = build_api()
# The api.py router of every app of ours: base (platform) and the modules of apps/.
mount_app_routers(api)
# The business's API keys (``erpk_live``, APP-BASE-5) open the routes of the operations the apps publish (``expose_api``).
api_keys.install(api)
