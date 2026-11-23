"""The business's apps (``base.app.list``, ``base.app.get``), the app a person names, and the state of their
activations."""

import datetime as dt
import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

from django.conf import settings
from django.db.models import Q, Min
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.meta import Category, module_configs
from live.operations import AI, INTERNAL, operation

from base import activation, business, entitlement, home
from base.auth import SAAS_PANEL_PATH, saas_url
from base.models.activation import AppActivation
from base.models import Hub
from base.permissions import VIEW_HOME
from base.schemas.apps import AppListIn, AppListOut, AppRefIn, AppRefOut


# ── Apps ───────────────────────────────────────────────────────────────────────────────────────────────────────


def app_off_refusal(  # noqa: PLR0913, PLR0917
    ctx: OperationContext,
    label: str,
    current: Mapping[str, activation.Activation],
    graph: activation.Graph,
    said: Mapping[str, str],
    kept: Iterable[str] = (),
) -> tuple[str, str] | None:
    """Why ``label`` can't go off because an app refuses, as ``(who refuses, what the person reads)``, from ``said``
    (``base.activation.refusals``); ``None`` when none of those it depends on does. Its own reason first: it holds
    whatever the others do (hub#997). One an app on needs says that app's reason, never «turn it off first», which
    nobody can do while it refuses (hub#619). ``kept`` never goes off along with it (``activation.mandatory_on``)."""
    keeping = activation.keeping_on(label, current, graph, kept)
    who = label if label in said else next((other for other in keeping if other in said), None)
    if who is None:
        return None
    if who not in activation.required_by(label, current, graph):
        return who, said[who]
    names = {config.label: config.verbose_name for config in module_configs()}
    with translation.override(ctx.language):
        return who, gettext("%(app)s can't be turned off: %(needed_by)s needs it. %(reason)s") % {
            "app": names[label],
            "needed_by": names[who],
            "reason": said[who],
        }


# Not an assistant tool: the Apps screen's own read; the assistant knows the apps by its catalogue.
@operation("base.app.list", kind="query", permission=VIEW_HOME, input=AppListIn, output=AppListOut, ai=INTERNAL)
def app_list(ctx: OperationContext, data: AppListIn) -> dict:
    """The Apps screen: every module the scope shows, from its own config in this process (never the
    SaaS's catalog), with where its right comes from and its state (``base.entitlement``: ``blocked`` without it;
    else ``on`` or ``off`` as the business turned it, ``base.activation``), whether the business chose it, the first
    screen this person may open, what it needs (it comes along with it) and the apps on that need it (they go off
    first), and why turning it on or off would be refused (the screen never offers what is always
    refused); and the plan's limit of chosen apps against the chosen ones on, erplora.com's Store and its
    plans of this business.

    Read again when an app's state changes (its live notice, in every process with the list open: AppsFollower on every
    screen). It reads the rows and leaves the cache as it is: every change of the apps forgets it at its COMMIT, in a
    cache every process shares (``base.cache``)."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    demo = bool(hub and hub.is_demo)
    configs = home.shown_modules(demo_hub=demo)
    shown = {config.label for config in configs}
    blocked = entitlement.blocked_apps(ctx.scope)
    rights = entitlement.entitlements(None if hub is None or hub.is_demo else hub.state, now=timezone.now())
    graph = activation.module_graph()
    current = activation.states_of(ctx.scope)
    needs = {config.label: entitlement.requires_of(config.label) for config in configs}
    # What the business's country requires on (hub#997): «Mandatory in …», and never off.
    country = hub.country if hub else ""
    kept = activation.mandatory_on(current, country)

    def state(label: str) -> str:
        if label in blocked:
            return "blocked"
        return current[label].state if current[label].wanted else "off"

    # Each hook once for the whole list: a row asking its own would read the business's country once per row.
    wont_go_off = activation.refusals(
        [label for label, row in current.items() if row.wanted], ctx=ctx, kept=kept, country=country
    )
    wont_go_on = activation.refusals(
        [label for label, row in current.items() if not row.on], ctx=ctx, hook=activation.CAN_ENABLE
    )

    def refusal(label: str) -> str | None:
        if label in blocked:
            return None
        if current[label].wanted:
            refused = app_off_refusal(ctx, label, current, graph, wont_go_off, kept)
            return refused[1] if refused else None
        coming = activation.enabling(label, current, graph)
        return next((wont_go_on[other] for other in coming if other in wont_go_on), None)

    with translation.override(ctx.language):
        return {
            "apps": [
                {
                    "id": config.label,
                    "name": str(config.verbose_name),
                    "icon": home.shell_icon(config),
                    "category": config.category,
                    "category_label": str(Category(config.category).label),
                    "summary": str(config.summary),
                    "premium": bool(config.premium),
                    "right": entitlement.FREE if demo else rights[config.label],
                    "state": state(config.label),
                    "chosen": current[config.label].wanted and current[config.label].chosen,
                    "path": _first_screen(ctx, config) if state(config.label) == "on" else None,
                    "requires": sorted(needs[config.label]),
                    "required_by": [
                        label for label in activation.required_by(config.label, current, graph) if label in shown
                    ],
                    "refusal": refusal(config.label),
                    "mandatory": home.mandatory_in(config, country),
                }
                for config in configs
            ],
            "country_name": business.country_name(business.country_or_market(country), ctx.language),
            "store_url": saas_url(f"{SAAS_PANEL_PATH}/store/modules?business={hub.id}") if hub is not None else "",
            "plan_url": saas_url(f"{SAAS_PANEL_PATH}/store/plans?business={hub.id}") if hub is not None and not demo else "",
            "max_apps": app_limit(hub),
            "enabled": activation.chosen_on(current, among=shown),
        }


#: What a name that is no app of the business answers (BASE-F24); one that fits several, ``APP_AMBIGUOUS``.
APP_NOT_FOUND = gettext_lazy("No app has that name or id.")
APP_AMBIGUOUS = gettext_lazy("“%(said)s” matches several apps: %(names)s. Say which one.")


def _plain(text: str) -> str:
    """``text`` as a name is compared: case and accents aside, its spaces collapsed."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(char for char in decomposed if not unicodedata.combining(char)).split())


def find_app(said: str, *, demo: bool, language: str) -> Any:
    """The app of the business ``said`` names, as a person says it (BASE-F23, F24; hub#539): its id; else the one whose
    name in a language of the Hub is ``said``, case and accents aside («reservas» is Reservas, never Reservas online
    beside it); else the only one with a word of its name that starts so («booking»). 404 when none (the platform is no
    app); 409 ``base.app_ambiguous`` naming them, in ``language``, when several (``reserva``): the person says which,
    as the apps' ``find_*`` of a table or a zone do."""
    configs = home.shown_modules(demo_hub=demo)
    plain = _plain(said)
    found = [config for config in configs if config.label == said.strip()]
    if not found and plain:
        named = {}
        for code, _ in settings.LANGUAGES:
            with translation.override(code):
                for config in configs:
                    named.setdefault(config.label, set()).add(_plain(str(config.verbose_name)))
        starts = re.compile(rf"(?:^|\W){re.escape(plain)}")
        found = [config for config in configs if plain in named[config.label]] or [
            config for config in configs if any(starts.search(name) for name in named[config.label])
        ]
    if not found:
        with translation.override(language):
            raise NotFound(str(APP_NOT_FOUND))
    if len(found) > 1:
        with translation.override(language):
            names = ", ".join(sorted(str(config.verbose_name) for config in found))
            raise Conflict(str(APP_AMBIGUOUS) % {"said": said.strip(), "names": names}, code="base.app_ambiguous")
    return found[0]


@operation(
    "base.app.get",
    kind="query",
    permission=VIEW_HOME,
    input=AppRefIn,
    output=AppRefOut,
    ai=AI(
        description=(
            "Says which of this business's apps a name names, as the person says it (e.g. «Reservas»), or an id: its "
            "id, its name and whether it is on, off, blocked (a paid app without its right), creating (being set up, "
            "on in a moment) or failed (it could not be set up: base.app.retry). mandatory=true: the business's country "
            "requires it, so once on it can't be turned off. A name that fits several apps is refused naming them: ask "
            "the person which one."
        ),
        asks={
            "en": ("is the reservations app on?", "what state is the website app in?", "do I have the kitchen app?"),
            "es": (
                "¿está activada la app de reservas?",
                "¿en qué estado está la app de la web?",
                "¿tengo la app de cocina?",
            ),
        },
    ),
)
def app_get(ctx: OperationContext, data: AppRefIn) -> dict:
    """Which app ``data.app`` names (``find_app``), with its state and whether the business's country requires it as the
    Apps screen says them: what the assistant's card of ``base.app.enable`` and ``base.app.disable`` names it by
    (``refers``), never by its id."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    config = find_app(data.app, demo=bool(hub and hub.is_demo), language=ctx.language)
    row = activation.states_of(ctx.scope)[config.label]
    state = "blocked" if config.label in entitlement.blocked_apps(ctx.scope) else row.state if row.wanted else "off"
    with translation.override(ctx.language):
        return {
            "id": config.label,
            "name": str(config.verbose_name),
            "state": state,
            "mandatory": home.mandatory_in(config, hub.country if hub else ""),
        }


def app_limit(hub: Hub | None) -> int | None:
    """The plan's limit of apps the business chooses (``plan.max_apps`` of its last photo); ``None``: no limit (none
    on a demo, which has no plan, nor on a host without its row)."""
    if hub is None or hub.is_demo:
        return None
    return activation.plan_limit(hub.state)


def app_activations(host: str) -> dict[str, activation.Activation]:
    """The rows of ``host``'s business (``base.activation.states_of`` reads them): empty while it never changed
    anything."""
    return {
        app: activation.Activation(state, chosen)
        for app, state, chosen in AppActivation.objects.filter(host=host).values_list("app", "state", "chosen")
    }


def activations_due(host: str, now: dt.datetime) -> dict[str, str]:
    """The apps of ``host``'s business whose tables the worker makes now, with the last migration the code that
    asked named (``target``): ``creating`` unless put off (a schema held, a newer code's request), or ``failed`` once
    its next try came."""
    due = Q(state=activation.CREATING) & (Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now)) | Q(
        state=activation.FAILED, next_attempt_at__lte=now
    )
    return dict(
        AppActivation.objects.filter(host=host, app__in=list(activation.module_graph()))
        .filter(due)
        .order_by("app")
        .values_list("app", "target")
    )


def activation_next_at(host: str) -> dt.datetime | None:
    """When the worker has to look into ``host``'s business next for apps to set up: now for one ``creating`` and not put
    off, else the earliest next try of one ``creating`` or ``failed``; ``None`` when none waits."""
    waiting = AppActivation.objects.filter(
        host=host, app__in=list(activation.module_graph()), state__in=[activation.CREATING, activation.FAILED]
    )
    if waiting.filter(state=activation.CREATING, next_attempt_at__isnull=True).exists():
        return timezone.now()
    return waiting.aggregate(next=Min("next_attempt_at"))["next"]


def activations_stuck(host: str, now: dt.datetime) -> int:
    """How many apps of ``host``'s business are stuck turning on: ``creating`` since it was asked
    for more than ``activation.STUCK_AFTER`` before ``now`` (``changed_at``: a schema held or a newer code's request
    puts it off without moving it), or ``failed``, at once: an error the business already sees, and each retry moves its
    ``changed_at``. Only the apps this code knows."""
    return (
        AppActivation.objects.filter(host=host, app__in=list(activation.module_graph()))
        .filter(Q(state=activation.CREATING, changed_at__lt=now - activation.STUCK_AFTER) | Q(state=activation.FAILED))
        .count()
    )


def _first_screen(ctx: OperationContext, config: Any) -> str | None:
    """The first entry of the module's menu the person may open; none if it may open none."""
    return next((nav.path for nav in open_entries(ctx, config)), None)


def open_entries(ctx: OperationContext, config: Any) -> list[Any]:
    """The entries of the module's menu the person may open: those whose permission it holds. One that names none
    opens to nobody (``ctx.has(None)`` is true; ``live.E025`` refuses such an entry at startup)."""
    return [nav for nav in config.navigation if nav.permission and ctx.has(nav.permission)]


def _can_see(ctx: OperationContext, config: Any) -> bool:
    """Whether the person sees the module in its menu and «My apps»: it may open one of its entries."""
    return bool(open_entries(ctx, config))


def _may_use(ctx: OperationContext, config: Any) -> bool:
    """Whether the person holds any permission of the module, which other screens use without opening it."""
    return ctx.has(f"{config.label}.view") or any(ctx.has(permission) for permission in config.permissions)
