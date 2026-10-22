"""The SPA's HTML for every path without a URL of its own in Django (last route of the URLconf).

Next to ``spa-config`` it embeds the result of ``base.session.me`` (``session-me``), so the shell
paints the menu and decides on the login without a first round trip. ``spa-config`` carries
``loginUrl``, ``/auth/login``, where the shell's auth gate sends (appending ``?next=``): the Hub's own
jump to the SaaS's login, which gives it its ``state``. ``hub-plan`` carries where this hub's plan is changed on the
SaaS (``/store/plans?business=<hub id>``): the menu's «Upgrade plan» (BASE-G169).
"""

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_safe
from live.ninja import run_operation_sync
from live.spa import render_spa

from base import queries
from base.auth import saas_url

SESSION_ME_ID = "session-me"
HUB_PLAN_ID = "hub-plan"


@require_safe
def spa(request: HttpRequest) -> HttpResponse:
    me = run_operation_sync(request, queries.session_me)
    extra_json = {SESSION_ME_ID: me.model_dump(mode="json")}
    hub = getattr(request, "hub", None)
    if hub is not None:
        extra_json[HUB_PLAN_ID] = {"url": saas_url(f"/store/plans?business={hub.id}")}
    return render_spa(
        request,
        extra_json=extra_json,
        extra_config={"loginUrl": reverse("auth-login")},
    )
