"""The SPA's HTML for every path without a URL of its own in Django (last route of the URLconf).

Next to ``spa-config`` it embeds the result of ``base.session.me`` (``session-me``), so the shell
paints the menu and decides on the login without a first round trip. ``spa-config`` carries
``loginUrl``, the SaaS's login for this hub, where the shell's auth gate sends (appending ``&next=``).
"""

from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_safe
from live.ninja import run_operation_sync
from live.spa import render_spa

from base import queries
from base.auth import login_url
from base.operations import HostScopeResolver

SESSION_ME_ID = "session-me"


@require_safe
def spa(request: HttpRequest) -> HttpResponse:
    me = run_operation_sync(request, queries.session_me)
    slug = HostScopeResolver().resolve(request).key
    return render_spa(
        request,
        extra_json={SESSION_ME_ID: me.model_dump(mode="json")},
        extra_config={"loginUrl": login_url(slug)},
    )
