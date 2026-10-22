"""The SPA's HTML for every path without a URL of its own in Django (last route of the URLconf).

Next to ``spa-config`` it embeds the result of ``base.session.me`` (``session-me``), so the shell
paints the menu and decides on the login without a first round trip. ``spa-config`` carries
``loginUrl``, ``/auth/login``, where the shell's auth gate sends (appending ``?next=``): the Hub's own
jump to the SaaS's login, which gives it its ``state``.

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

SESSION_ME_ID = "session-me"


@require_safe
def spa(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated and request.path_info == "/" and public_home.website_enabled(request):
        return public_home.respond(request)
    return _shell(request)


def _shell(request: HttpRequest) -> HttpResponse:
    """The SPA's HTML (``render_spa``: never cached, with the CSRF cookie the SDK sends back)."""
    me = run_operation_sync(request, queries.session_me)
    return render_spa(
        request,
        extra_json={SESSION_ME_ID: me.model_dump(mode="json")},
        extra_config={"loginUrl": reverse("auth-login")},
    )
