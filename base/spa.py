"""The SPA's HTML for every path without a URL of its own in Django (last route of the URLconf).

Next to ``spa-config`` it embeds the result of ``base.session.me`` (``session-me``), so the shell
paints the menu and decides on the login without a first round trip. ``spa-config`` carries
``loginUrl``, ``/auth/login``, where the shell's auth gate sends (appending ``?next=``): the Hub's own
jump to the SaaS's login, which gives it its ``state``. ``hub-home`` carries this hub's name (the SaaS's, which heads the
Home, BASE-G127) and where its plan is changed on the SaaS (``/store/plans?business=<hub id>``, the menu's «Upgrade
plan», BASE-G169).

``spa`` is the view ``base.middleware`` knows by identity; it dispatches. A visitor without a session who loads
``/`` of a hub with a published website gets that website (``base.public_home``), which never passes through
``render_spa``: no CSRF cookie, no ``never_cache``. Everyone else gets the shell.
"""

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_safe
from live.ninja import run_operation_sync
from live.spa import render_spa

from base import public_home, queries
from base.auth import saas_url

SESSION_ME_ID = "session-me"
HUB_HOME_ID = "hub-home"


@require_safe
def spa(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated and request.path_info == "/" and public_home.website_enabled(request):
        return public_home.respond(request)
    return _shell(request)


def _shell(request: HttpRequest) -> HttpResponse:
    """The SPA's HTML (``render_spa``: never cached, with the CSRF cookie the SDK sends back)."""
    me = run_operation_sync(request, queries.session_me)
    extra_json = {SESSION_ME_ID: me.model_dump(mode="json")}
    hub = getattr(request, "hub", None)
    if hub is not None:
        extra_json[HUB_HOME_ID] = {"name": hub.name, "plan_url": saas_url(f"/store/plans?business={hub.id}")}
    return render_spa(
        request,
        extra_json=extra_json,
        extra_config={"loginUrl": reverse("auth-login")},
    )
