"""The SPA's HTML for every path without a URL of its own in Django (last route of the URLconf).

Next to ``spa-config`` it embeds the result of ``base.session.me`` (``session-me``), so the shell
paints the menu and decides on the login without a first round trip. ``spa-config`` carries
``loginUrl``, ``/auth/login``, where the shell's auth gate sends (appending ``?next=``): the Hub's own
jump to the SaaS's login, which gives it its ``state``. ``hub-home`` carries this hub's name (the SaaS's, which heads the
Home, BASE-G127), where its plan is changed on the SaaS (``/dashboard/store/plans?business=<hub id>``, the menu's «Upgrade
plan», BASE-G169), the SaaS's account page (the user menu's «My account», PLAN-SAAS §1.1; its «Report a problem» is the
hub's own dialog, BASE-F108, offered where «My account» is) and this business on
the SaaS's panel (``manage_url``, the bar's «erplora.com», BASE-F11; only with ``base.open_management``), those only
to a session opened with the account, and the session's way in (``access``: «Switch user», the idle lock; APP-BASE-3,
``base.queries.shell_access``) and the person's own appearance (``preferences``, BASE-G125). ``widget-list`` carries
``base.widget.list`` as its live query answers it to this person: the Home's board mounts its panels with it, so their
data goes in the same live stream as the list instead of reopening it on every load (the live answer then wins). Both
go only to a person with a session: the auth gate sends anyone else to the login, so their HTML names neither the
business nor the hub's id.

``spa`` is the view ``base.middleware`` knows by identity; it dispatches. A visitor without a session who loads
``/`` of a hub with a published website gets that website (``base.public_home``), which never passes through
``render_spa``: no CSRF cookie, no ``never_cache``. Everyone else gets the shell.

A path that names a file (:data:`NOT_A_FILE`: ``/robots.txt``, ``/favicon.ico``, ``/wp-login.php``) is no route of
the SPA (:func:`spa_route`): without a URL of its own it gets Django's plain 404, with no shell and no cookie, with a
session or without and whatever it accepts. A crawler reads no HTML as the hub's ``robots.txt`` (a 404 there means
«no rules»), and a browser's ``/favicon.ico`` leaves no ``csrftoken`` on the website's visitor.
"""

from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.views.decorators.http import require_safe
from live.context import get_builder
from live.errors import OperationError
from live.ninja import run_operation_sync
from live.spa import render_spa, spa_path_pattern

from base import public_home, queries
from base.auth import SAAS_PANEL_PATH, saas_url
from base.models import SessionOwner

SESSION_ME_ID = "session-me"
HUB_HOME_ID = "hub-home"
WIDGET_LIST_ID = "widget-list"
#: Who may open this business on erplora.com's panel from the bar (``base/apps.py``: owner, admin and manager).
OPEN_MANAGEMENT = "base.open_management"
#: A path whose last segment has an extension names a file, and no route of the SPA looks like one (its parameters
#: are ids). It is the fallback rule of connect-history-api-fallback and of ASP.NET Core's ``{*path:nonfile}``. With a
#: trailing slash too: else ``APPEND_SLASH`` would send ``/robots.txt`` to ``/robots.txt/``, and that to the shell.
NOT_A_FILE = r"(?!.*\.[^/]*/?$)"


def spa_route(prefixes: tuple[str, ...]) -> str:
    """The SPA's ``re_path``: every path ``live.spa.spa_path_pattern(prefixes)`` leaves it, save a file's."""
    return rf"^{NOT_A_FILE}{spa_path_pattern(prefixes)}"


@require_safe
def spa(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated and request.path_info == "/" and public_home.website_enabled(request):
        return public_home.respond(request)
    return _shell(request)


def _widgets(request: HttpRequest) -> dict | None:
    """``base.widget.list`` as its live query answers it to this person, or ``None`` when it refuses them (no Home for
    them): then the board waits for the live answer, as it did before."""
    try:
        return run_operation_sync(request, queries.widget_list).model_dump(mode="json")
    except OperationError:
        return None


def _may_manage(request: HttpRequest) -> bool:
    """Whether this person may open the business on erplora.com's panel (their permissions, as an operation reads them)."""
    return get_builder().from_request(request).has(OPEN_MANAGEMENT)


def _shell(request: HttpRequest) -> HttpResponse:
    """The SPA's HTML (``render_spa``: never cached, with the CSRF cookie the SDK sends back)."""
    me = run_operation_sync(request, queries.session_me)
    extra_json = {SESSION_ME_ID: me.model_dump(mode="json")}
    hub = getattr(request, "hub", None)
    if hub is not None and request.user.is_authenticated:
        way_in = queries.shell_access(request, hub.slug)
        # erplora.com's pages only for a session opened with the account: on a shared till, the browser's erplora.com
        # session is whoever made it a device of the hub, never the person who entered with a PIN (gh:hub#2506).
        account = way_in["credential"] == SessionOwner.Credential.ACCOUNT
        extra_json[HUB_HOME_ID] = {
            "name": hub.name,
            "plan_url": saas_url(f"{SAAS_PANEL_PATH}/store/plans?business={hub.id}") if account else "",
            "account_url": saas_url(f"{SAAS_PANEL_PATH}/account") if account else "",
            # APP-BASE-5: «Members» of the business on erplora.com (HUBS-F24…F29), where people are invited.
            "members_url": saas_url(f"{SAAS_PANEL_PATH}/businesses/{hub.id}/members") if account else "",
            # BASE-F11: the bar's «erplora.com», this business on the panel, for who runs it (gh:hub#364).
            "manage_url": saas_url(f"{SAAS_PANEL_PATH}/businesses/{hub.id}") if account and _may_manage(request) else "",
            "access": way_in,
            "preferences": queries.appearance_of(request.user),
        }
        widgets = _widgets(request)
        if widgets is not None:
            extra_json[WIDGET_LIST_ID] = widgets
    return render_spa(
        request,
        extra_json=extra_json,
        extra_config={"loginUrl": reverse("auth-login")},
    )
