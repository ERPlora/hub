"""URLconf of hub-next: Django's own prefixes first, then the SPA for every other path.

``/healthz`` is answered by ``base.health.HealthCheckMiddleware`` before the Host is validated,
so it has no route here; ``/readyz`` (it reads the database) is a route on the real hosts.
"""

from django.contrib import admin
from django.urls import path, re_path
from django.utils.translation import gettext_lazy
from live.csp import csp_report
from live.live_view import live_stream
from live.spa import BASE_NON_SPA_PREFIXES, spa_path_pattern

from base.admin import open_hub
from base.auth_views import auth_callback, auth_login, auth_logout
from base.health import readyz
from base.internal import (
    demo_codes,
    demos,
    hub,
    hub_restore,
    hub_state,
    platform_invoice_create,
    platform_invoice_get,
    platform_invoice_pdf,
    platform_invoices_health,
    sessions_revoke,
    whatsapp_channel,
    whatsapp_inbound,
    whatsapp_status,
)
from base.media import media
from base.spa import spa
from config.api import api

# Prefixes of hub-next on top of the shared ones: the print socket, the public pages and the login
# through the SaaS.
NON_SPA_PREFIXES = (*BASE_NON_SPA_PREFIXES, "ws", "p", "auth")

# ERPlora's name on every page of the staff's admin, never «Django administration» (as the SaaS's admin does).
admin.site.site_header = "ERPlora Hub"
admin.site.site_title = "ERPlora Hub Admin"
admin.site.index_title = gettext_lazy("Administration")

urlpatterns = [
    # The deep link of the SaaS admin's «Open in the Hub admin» (PLAN §18.1); before the admin's own
    # admin/<app_label>/, which would otherwise take it.
    path("admin/hub/<str:slug>/", admin.site.admin_view(open_hub), name="admin-hub"),
    path("admin/", admin.site.urls),
    # Before the API's prefix, which would otherwise answer it.
    path("api/live", live_stream, name="live-stream"),
    path("api/", api.urls),
    path("csp-report/", csp_report, name="csp-report"),
    path("readyz", readyz, name="readyz"),
    path("auth/login", auth_login, name="auth-login"),
    path("auth/callback", auth_callback, name="auth-callback"),
    path("auth/logout", auth_logout, name="auth-logout"),
    path("internal/demos", demos, name="internal-demos"),
    path("internal/demos/<str:slug>/codes", demo_codes, name="internal-demo-codes"),
    path("internal/hubs/<uuid:hub_id>", hub, name="internal-hub"),
    path("internal/hubs/<uuid:hub_id>/restore", hub_restore, name="internal-hub-restore"),
    path("internal/hubs/<uuid:hub_id>/state", hub_state, name="internal-hub-state"),
    path("internal/sessions/revoke", sessions_revoke, name="internal-sessions-revoke"),
    path("internal/platform/invoices", platform_invoice_create, name="internal-platform-invoices"),
    path(
        "internal/platform/invoices/health",
        platform_invoices_health,
        name="internal-platform-invoices-health",
    ),
    path(
        "internal/platform/invoices/<uuid:invoice_id>",
        platform_invoice_get,
        name="internal-platform-invoice",
    ),
    path(
        "internal/platform/invoices/<uuid:invoice_id>/pdf",
        platform_invoice_pdf,
        name="internal-platform-invoice-pdf",
    ),
    path("internal/whatsapp/inbound", whatsapp_inbound, name="internal-whatsapp-inbound"),
    path("internal/whatsapp/status", whatsapp_status, name="internal-whatsapp-status"),
    path("internal/whatsapp/channel", whatsapp_channel, name="internal-whatsapp-channel"),
    # The hub file store's files (base.media), on the hub's own host; /p is the public pages' prefix.
    path("p/media/<str:hub>/<path:name>", media, name="media"),
    re_path(spa_path_pattern(NON_SPA_PREFIXES), spa, name="spa"),
]
