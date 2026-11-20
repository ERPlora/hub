"""The Home's live queries (``base.setup.status``, ``base.widget.list``, ``base.bell.counters``), the device's notices
and System's cards; their rules are ``base.home``'s."""

from django.utils import translation
from django.utils.translation import gettext_lazy
from live.context import OperationContext
from live.operations import AI, INTERNAL, operation

from base import activation, bell, home
from base.apps_on import active_apps
from base.models import EventDelivery, Hub, Membership
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas.home import (
    NoticeListIn,
    NoticeListOut,
    SetupStatusIn,
    SetupStatusOut,
    SystemCardsIn,
    SystemCardsOut,
    WidgetListIn,
    WidgetListOut,
)
from base.schemas.bell import BellCountersIn, BellCountersOut

from .usage import _plan_motives


# --- The Home ---------------------------------------------------------------------------------------------------


@operation(
    "base.setup.status",
    kind="query",
    permission=VIEW_HOME,
    input=SetupStatusIn,
    output=SetupStatusOut,
    ai=AI(
        description=(
            "Reads the checklist «Finish setting up your business» of this hub, as this person may see it: each step "
            "with its state (done, pending, or not available — ours, never something to ask the person to do), its "
            "level (needed to invoice, important, recommended), whether the person can set it up (otherwise an "
            "administrator must) and the screen that completes it; with how many are pending."
        ),
        asks={
            "en": ("what's left to set up?", "am I ready to invoice yet?", "what's still pending on the checklist?"),
            "es": (
                "¿qué me falta por configurar?",
                "¿ya puedo facturar?",
                "¿qué queda pendiente para terminar de montar el negocio?",
            ),
        },
    ),
)
def setup_status(ctx: OperationContext, data: SetupStatusIn) -> dict:
    """The old hub's ``hub.setup.status``: the platform's steps (``base.apps``, ``base.mandatory.<app>``, ``base.team``)
    and the modules'."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        on = active_apps(ctx.scope)
        demo_hub = bool(hub and hub.is_demo)
        country = hub.country if hub else ""
        modules = home.home_modules(on, demo_hub=demo_hub)
        items = _platform_steps(ctx, on, country, demo_hub) + home.module_steps(ctx, modules, country)
        return home.document(items)


def _platform_steps(ctx: OperationContext, on: frozenset[str], country: str, demo_hub: bool) -> list[dict]:
    """«Your apps» (some business app on, but those its country's businesses are born with: with them alone the till has
    nothing to sell, hub#997), «Turn on <app>» for each app mandatory in the business's ``country`` that is off (hub#997)
    and «Your team» (more than one active person), for who runs the hub: who turns apps on and off."""
    if not ctx.has(ADMINISTER_HUB):
        return []
    business_apps = home.business_apps()
    born = activation.born_apps(country)
    if any(label in on and label not in born for label in business_apps):
        apps_state = home.STATE_DONE
    else:
        apps_state = home.STATE_PENDING if business_apps else home.STATE_UNAVAILABLE
    people = Membership.objects.filter(host=ctx.scope.key, user__is_active=True).count()
    return [
        home.item(
            "base.apps",
            "base",
            state=apps_state,
            required=True,
            level=home.level_of("base.apps", True),
            actionable=True,
            title=gettext_lazy("Your apps"),
            description=gettext_lazy("Turn on at least one business app so your till has something to sell."),
            icon="ion:grid-outline",
            route="/apps",
            order=10,
        ),
        *home.mandatory_steps(home.shown_modules(demo_hub=demo_hub), on, country),
        home.item(
            "base.team",
            "base",
            state=home.STATE_DONE if people > 1 else home.STATE_PENDING,
            required=False,
            level=home.level_of("base.team", False),
            actionable=True,
            title=gettext_lazy("Your team"),
            description=gettext_lazy("Add the people who will use the till, each with their own way in."),
            icon="ion:people-outline",
            route="/employees",
            order=80,
        ),
    ]


# Not an assistant tool: the Home's panels, the screen's own layout.
@operation(
    "base.widget.list",
    kind="query",
    permission=VIEW_HOME,
    input=WidgetListIn,
    output=WidgetListOut,
    ai=INTERNAL,
)
def widget_list(ctx: OperationContext, data: WidgetListIn) -> dict:
    """The panels of the apps on that this person may see, of the hub's vertical; the SPA follows each one's data."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        configs = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        return {"widgets": home.widgets(ctx, configs, hub.vertical if hub else "")}


# Not an assistant tool: the cards of System, the screen's own layout (each card reads what it says by its app's queries).
@operation(
    "base.system.cards",
    kind="query",
    permission=VIEW_HOME,
    input=SystemCardsIn,
    output=SystemCardsOut,
    ai=INTERNAL,
)
def system_cards(ctx: OperationContext, data: SystemCardsIn) -> dict:
    """The cards the apps on put in System › «Usage and plan» that this person may see (hub#683): Printing's «Your
    printer» while Printing is on, none while it is off."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    configs = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
    return {"cards": home.system_cards(ctx, configs)}


# Not an assistant tool: the bell's counters, the screen's own chrome.
@operation(
    "base.bell.counters",
    kind="query",
    permission=VIEW_HOME,
    input=BellCountersIn,
    output=BellCountersOut,
    ai=INTERNAL,
)
def bell_counters(ctx: OperationContext, data: BellCountersIn) -> dict:
    """The bell: the counters above zero of the apps on, and for who runs the hub the events the relay gave up on and
    the reasons to upgrade its plan (BASE-F40)."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        modules = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        counters = home.bell_counters(ctx, modules)
        if ctx.has(ADMINISTER_HUB):
            failed = EventDelivery.objects.filter(
                status=EventDelivery.Status.DEAD,
                event__scope_kind=ctx.scope.kind,
                event__scope_key=ctx.scope.key,
            ).count()
            motives = _plan_motives(ctx, hub, modules)
            if motives:
                counters.insert(0, bell.notice("base.plan_limits", bell.PLAN_LIMITS, {"count": motives}))
            if failed:
                counters.insert(0, bell.notice("base.failed_events", bell.FAILED_EVENTS, {"count": failed}))
        return {"counters": counters, "refresh_every": home.bell_refresh_every(ctx, modules)}


# Not an assistant tool: the device's notices, which the device itself shows.
@operation(
    "base.notice.list",
    kind="query",
    permission=VIEW_HOME,
    input=NoticeListIn,
    output=NoticeListOut,
    ai=INTERNAL,
)
def notice_list(ctx: OperationContext, data: NoticeListIn) -> dict:
    """The device's notices: the rows the modules on tell, with their texts filled in."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        modules = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        return {"notices": home.device_notices(ctx, modules), "sources": home.notice_sources(ctx, modules)}
