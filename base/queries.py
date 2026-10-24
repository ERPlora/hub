"""Read operations of base: the session's ``me``, the registry's row of a hub (``base.hub.get``), a demo's status
(``base.demo.get``) and the Home's three live queries (``base.setup.status``, ``base.widget.list``,
``base.bell.counters``; their rules are ``base.home``'s)."""

from typing import Any

from django.conf import settings
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy, ngettext
from live.context import OperationContext
from live.errors import NotFound
from live.meta import Category
from live.models import OutboxEvent
from live.operations import operation

from base import entitlement, home, system
from base.auth import saas_url
from base.models import EventDelivery, Hub, Membership
from base.registry import hub_answer, internal_only
from base.relay import active_apps
from base.schemas import (
    AppListIn,
    AppListOut,
    BellCountersIn,
    BellCountersOut,
    DemoSlugIn,
    DemoStatusOut,
    EventListIn,
    EventListOut,
    FailedEventListIn,
    FailedEventListOut,
    HubGetIn,
    HubOut,
    HubsBySlugIn,
    HubsBySlugOut,
    NoticeListIn,
    NoticeListOut,
    PlanUsageIn,
    PlanUsageOut,
    SessionMeIn,
    SessionMeOut,
    SetupStatusIn,
    SetupStatusOut,
    SystemStatusIn,
    SystemStatusOut,
    WidgetListIn,
    WidgetListOut,
)

#: Everyone of the hub sees the Home; who runs it (owner, admin) is told the platform's steps and counters.
VIEW_HOME = "base.view_home"
ADMINISTER_HUB = "base.administer_hub"


@operation("base.session.me", kind="query", permission=None, input=SessionMeIn, output=SessionMeOut)
def session_me(ctx: OperationContext, data: SessionMeIn) -> dict[str, Any]:
    """The user, its permissions, and the menu and apps it may see on this scope, already translated.

    Menu and apps list modules only (``home.shown_modules``: the reference app only in development, the tests
    or a demo's hub): a platform app such as ``base`` is always on and never shows. A module its business has no
    right to (``base.entitlement``) is ``off`` and has no menu: the shell's gate tells why its screens do not open. ``demo`` says when the demo
    ends, on a demo's hub only. No permission: an anonymous visitor gets ``user: None`` and nothing else, which
    tells the SPA to send it to the login.
    """
    # Labels are lazy translations; a live re-run happens outside the request that activated the
    # language, so it is set here.
    demo = _demo_hub(ctx)
    blocked = entitlement.blocked_apps(ctx.scope)
    with translation.override(ctx.language):
        visible = [config for config in home.shown_modules(demo_hub=demo is not None) if _can_see(ctx, config)]
        return {
            "user": _user(ctx.actor),
            "scope": {"kind": ctx.scope.kind, "key": ctx.scope.key},
            "permissions": sorted(ctx.permissions),
            "menu": [
                {
                    "id": config.label,
                    "label": str(config.verbose_name),
                    "items": [
                        {"path": nav.path, "label": str(nav.label), "icon": nav.icon} for nav in config.navigation
                    ],
                }
                for config in visible
                if config.navigation and config.label not in blocked
            ],
            "apps": [{"label": config.label, "state": "off" if config.label in blocked else "on"} for config in visible],
            "language": ctx.language,
            "demo": None if demo is None else {"expires_at": demo.expires_at},
        }


def _demo_hub(ctx: OperationContext) -> Hub | None:
    """The demo's hub of this scope (its end, plan 2026-10-17, §1.6, and the reference app it shows), or ``None``
    on a business's hub."""
    if ctx.scope.kind != "host":
        return None
    return Hub.objects.filter(slug=ctx.scope.key, is_demo=True).first()


def _can_see(ctx: OperationContext, config: Any) -> bool:
    return ctx.has(f"{config.label}.view") or any(ctx.has(permission) for permission in config.permissions)


def _user(actor: Any) -> dict[str, str] | None:
    if actor is None:
        return None
    if not hasattr(actor, "get_username"):  # the platform itself (live.context.system_context)
        return {"id": str(actor), "label": str(actor)}
    return {"id": str(actor.pk), "label": actor.get_full_name() or actor.get_username()}


@operation("base.hub.get", kind="query", permission=None, input=HubGetIn, output=HubOut)
def hub_get(ctx: OperationContext, data: HubGetIn) -> dict[str, Any]:
    """The registry's row of ``data.id`` (``GET /internal/hubs/{id}``), for the platform only: the SaaS asks it about
    a sign-up whose ``ready`` it never heard, and marks it ready when ``status`` is ``ready``."""
    internal_only(ctx)
    hub = Hub.objects.filter(pk=data.id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    return hub_answer(hub)


@operation("base.hub.by_slugs", kind="query", permission=None, input=HubsBySlugIn, output=HubsBySlugOut)
def hubs_by_slugs(ctx: OperationContext, data: HubsBySlugIn) -> dict[str, Any]:
    """The registry's status of each of ``data.slugs`` (``None`` without a row), in their order, for the platform
    only: ``seed_local_hubs --check`` asks it about ``a`` and ``b``."""
    internal_only(ctx)
    found = dict(Hub.objects.filter(slug__in=data.slugs).values_list("slug", "status"))
    return {"hubs": [{"slug": slug, "status": found.get(slug)} for slug in data.slugs]}


@operation("base.demo.get", kind="query", permission=None, input=DemoSlugIn, output=DemoStatusOut)
def demo_get(ctx: OperationContext, data: DemoSlugIn) -> dict[str, Any]:
    """The status of the demo ``data.slug``, for the platform only: ``manage.py demo_expire`` says it once done."""
    internal_only(ctx)
    hub = Hub.objects.filter(slug=data.slug, is_demo=True).first()
    if hub is None:
        raise NotFound(gettext("No demo has this address."))
    return {"slug": hub.slug, "status": hub.status, "expires_at": hub.expires_at}


# --- The Home (PLAN-HUB round 2026-10-21) -----------------------------------------------------------------------


@operation(
    "base.setup.status",
    kind="query",
    permission=VIEW_HOME,
    input=SetupStatusIn,
    output=SetupStatusOut,
    ai={
        "description": "Reads the checklist «Finish setting up your business» of this hub, as this person may see "
        "it: each step with its state (done, pending, or not available — ours, never something to ask the person "
        "to do), its level (needed to invoice, important, recommended), whether the person can set it up "
        "(otherwise an administrator must) and the screen that completes it; with how many are pending."
    },
)
def setup_status(ctx: OperationContext, data: SetupStatusIn) -> dict:
    """The old hub's ``hub.setup.status``: the platform's steps (``base.apps``, ``base.team``) and the modules'."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        on = active_apps(ctx.scope)
        modules = home.home_modules(on, demo_hub=bool(hub and hub.is_demo))
        items = _platform_steps(ctx, on) + home.module_steps(ctx, modules, hub.country if hub else "")
        return home.document(items)


def _platform_steps(ctx: OperationContext, on: frozenset[str]) -> list[dict]:
    """«Your apps» (some business app on) and «Your team» (more than one active person), for who runs the hub."""
    if not ctx.has(ADMINISTER_HUB):
        return []
    business_apps = home.business_apps()
    if any(label in on for label in business_apps):
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


@operation("base.widget.list", kind="query", permission=VIEW_HOME, input=WidgetListIn, output=WidgetListOut)
def widget_list(ctx: OperationContext, data: WidgetListIn) -> dict:
    """The panels of the apps on that this person may see, of the hub's vertical; the SPA follows each one's data."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        configs = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        return {"widgets": home.widgets(ctx, configs, hub.vertical if hub else "")}


@operation("base.bell.counters", kind="query", permission=VIEW_HOME, input=BellCountersIn, output=BellCountersOut)
def bell_counters(ctx: OperationContext, data: BellCountersIn) -> dict:
    """The bell: the counters above zero of the apps on, and for who runs the hub the events the relay gave up on."""
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
            if failed:
                counters.insert(
                    0,
                    {
                        "key": "base.failed_events",
                        "app": "base",
                        "count": failed,
                        "route": "/system#events",
                        "label": gettext("Failed events"),
                        "icon": "ion:warning-outline",
                    },
                )
        return {"counters": counters}


@operation("base.notice.list", kind="query", permission=VIEW_HOME, input=NoticeListIn, output=NoticeListOut)
def notice_list(ctx: OperationContext, data: NoticeListIn) -> dict:
    """The device's notices (PLAN-HUB round 2026-10-23): the rows the modules on tell, with their texts filled in."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        modules = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        return {"notices": home.device_notices(ctx, modules), "sources": home.notice_sources(ctx, modules)}


# ── Apps (APP-BASE-4) ──────────────────────────────────────────────────────────────────────────────────────────


@operation("base.app.list", kind="query", permission=VIEW_HOME, input=AppListIn, output=AppListOut)
def app_list(ctx: OperationContext, data: AppListIn) -> dict:
    """The Apps screen: every module the scope shows, from its own config in this process (PLAN §20.4.1; never the
    SaaS's catalog), with where its right comes from and its state (``base.entitlement``), the first screen this
    person may open, what it needs (it comes along with it) and what needs it, and erplora.com's Store of this
    business, where a paid one is bought. Phase 1 has every module the business has a right to on."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    configs = home.shown_modules(demo_hub=bool(hub and hub.is_demo))
    blocked = entitlement.blocked_apps(ctx.scope)
    rights = entitlement.entitlements(None if hub is None or hub.is_demo else hub.state, now=timezone.now())
    needs = {config.label: entitlement.requires_of(config.label) for config in configs}
    with translation.override(ctx.language):
        return {
            "apps": [
                {
                    "id": config.label,
                    "name": str(config.verbose_name),
                    "icon": _shell_icon(config),
                    "category": config.category,
                    "category_label": str(Category(config.category).label),
                    "summary": str(config.summary),
                    "premium": bool(config.premium),
                    "right": entitlement.FREE if hub is not None and hub.is_demo else rights[config.label],
                    "state": "blocked" if config.label in blocked else "on",
                    "path": None if config.label in blocked else _first_screen(ctx, config),
                    "requires": sorted(needs[config.label]),
                    "required_by": sorted(label for label, required in needs.items() if config.label in required),
                }
                for config in configs
            ],
            "store_url": saas_url(f"/store/modules?business={hub.id}") if hub is not None else "",
        }


def _shell_icon(config: Any) -> str:
    """The icon the shell paints for a module: its first menu entry's, as the launcher and «My apps»; without a menu,
    the shell's own for an app. The module's ``icon`` is the store's, baked apart (``base.catalog``): HubIcon refuses
    a name the shell has not registered."""
    return config.navigation[0].icon if config.navigation else "ion:apps-outline"


def _first_screen(ctx: OperationContext, config: Any) -> str | None:
    """The first entry of the module's menu, for a person who may see the module; else none."""
    if not config.navigation or not _can_see(ctx, config):
        return None
    return config.navigation[0].path


@operation("base.plan.usage", kind="query", permission=ADMINISTER_HUB, input=PlanUsageIn, output=PlanUsageOut)
def plan_usage(ctx: OperationContext, data: PlanUsageIn) -> dict:
    """«Plan and limits» of System (BASE-G81): the limits of the plan the SaaS's last photo carries (``plan``:
    ``max_users``, ``max_devices``; 0 = no limit) against the people of the business (its active members, the ones
    the SaaS counts). Devices: the limit only, the Hub keeps no count of them yet. Memory, CPU and database size are
    gone with the old process per hub (PLAN-HUB §1a): erplora.com measures the use. For who runs the business."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    state = hub.state if hub is not None and isinstance(hub.state, dict) else {}
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else None
    known = plan is not None and all(_is_count(plan.get(field)) for field in ("max_users", "max_devices"))
    people = Membership.objects.filter(host=ctx.scope.key, user__is_active=True).count()
    return {
        "known": known,
        "people": {"used": people, "limit": _limit(plan, "max_users") if known else None},
        "devices": {"used": None, "limit": _limit(plan, "max_devices") if known else None},
    }


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _limit(plan: dict, field: str) -> int | None:
    """A limit of the plan; 0 is none."""
    return plan[field] or None


# ── System (APP-BASE-7) ────────────────────────────────────────────────────────────────────────────────────────
# The old hub's ``GET /api/system`` (its status and its log) and ``/api/hub/events/dead`` (the failed events), for who
# runs the business only (hub#2519: an error may carry a customer's tax id and name). One hub never sees another's.

#: How many of the last events between apps System › Logs shows: the old hub's.
EVENT_LOG_SIZE = 50
#: How much of a failed event's last error the list carries: its start tells it, and the page stays light.
FAILED_EVENT_ERROR_LENGTH = 300


@operation(
    "base.system.status",
    kind="query",
    permission=ADMINISTER_HUB,
    input=SystemStatusIn,
    output=SystemStatusOut,
    ai={
        "description": "Reads the status of this hub's system: the version of ERPlora it runs and when that version "
        "was published (the hub updates itself, nobody installs anything), and whether its data is on the database "
        "every business shares or on its own. CPU, memory and connections are not measured per business."
    },
)
def system_status(ctx: OperationContext, data: SystemStatusIn) -> dict:
    """The release (``base.system``: the commit, short) and its date, never made up, and where the business's data
    lives (``Hub.db_name`` empty: phase 1's shared database)."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    return {
        "version": system.version(settings.APP_VERSION),
        "released_at": system.released_at(settings.APP_RELEASED_AT),
        "shared_database": not (hub is not None and hub.db_name),
    }


@operation(
    "base.event.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=EventListIn,
    output=EventListOut,
    ai={
        "description": "Reads the log of the last 50 events between this hub's apps (a sale charged, a round "
        "fired…), newest first: when each happened, which app recorded it, its level (info, warning, error) and "
        "what happened to it (delivered to each app, retrying, given up and waiting in «Failed events», "
        "discarded). Never the content of an event."
    },
)
def event_list(ctx: OperationContext, data: EventListIn) -> dict:
    """The old hub's System › Logs: the hub's last outbox events with how their deliveries went (``base.relay``)."""
    with translation.override(ctx.language):
        recent = list(
            OutboxEvent.objects.filter(scope_kind=ctx.scope.kind, scope_key=ctx.scope.key).order_by(
                "-created_at", "-id"
            )[:EVENT_LOG_SIZE]
        )
        deliveries: dict[Any, list[EventDelivery]] = {}
        for delivery in EventDelivery.objects.filter(event_id__in=[event.pk for event in recent]).order_by(
            "app_label"
        ):
            deliveries.setdefault(delivery.event_id, []).append(delivery)
        return {"entries": [_log_entry(event, deliveries.get(event.pk, [])) for event in recent]}


def _log_entry(event: OutboxEvent, deliveries: list[EventDelivery]) -> dict:
    app = event.name.split(".", 1)[0]
    if not deliveries:
        detail = gettext("No app listens to it.") if event.delivered_at else gettext("Waiting to be handed to the apps.")
        return _entry(event, app, "info", detail)
    statuses = {delivery.status for delivery in deliveries}
    if EventDelivery.Status.DEAD in statuses:
        level = "error"
    elif any(delivery.status == EventDelivery.Status.PENDING and delivery.attempts for delivery in deliveries):
        level = "warning"
    else:
        level = "info"
    return _entry(event, app, level, " ".join(_delivery_detail(delivery) for delivery in deliveries))


def _entry(event: OutboxEvent, app: str, level: str, detail: str) -> dict:
    return {
        "id": event.pk,
        "at": event.created_at,
        "level": level,
        "name": event.name,
        "app": app,
        "app_name": system.app_name(app),
        "detail": detail,
    }


def _delivery_detail(delivery: EventDelivery) -> str:
    """What happened to one app's delivery; the error itself stays in Failed events."""
    app = system.app_name(delivery.app_label)
    if delivery.status == EventDelivery.Status.DELIVERED:
        return gettext("Delivered to %(app)s.") % {"app": app}
    if delivery.status == EventDelivery.Status.DEAD:
        return gettext("%(app)s could not take it: it is in Failed events.") % {"app": app}
    if delivery.status == EventDelivery.Status.DISCARDED:
        return gettext("Discarded for %(app)s.") % {"app": app}
    if delivery.attempts:
        return ngettext(
            "%(app)s failed %(count)d time; it is retried by itself.",
            "%(app)s failed %(count)d times; it is retried by itself.",
            delivery.attempts,
        ) % {"app": app, "count": delivery.attempts}
    return gettext("Waiting for %(app)s.") % {"app": app}


@operation(
    "base.failed_event.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=FailedEventListIn,
    output=FailedEventListOut,
    ai={
        "description": "Lists the failed events of this hub, newest first: messages between apps (a sale to "
        "Invoicing, a round to Printing…) that could not be delivered after every retry. Each one says the event, "
        "the app that sent it and the one that could not take it, the attempts, when it happened, the start of the "
        "last error and whether it can be resent (not when the app it was for is no longer on). Pages of up to 100."
    },
)
def failed_event_list(ctx: OperationContext, data: FailedEventListIn) -> dict:
    """The deliveries the relay gave up on (``dead``) of the hub; a resent one is ``pending`` again and a discarded one
    is closed: neither is here."""
    with translation.override(ctx.language):
        failed = EventDelivery.objects.filter(
            status=EventDelivery.Status.DEAD, event__scope_kind=ctx.scope.kind, event__scope_key=ctx.scope.key
        )
        page = failed.select_related("event").order_by("-event__created_at", "-id")[
            data.offset : data.offset + data.limit
        ]
        on = active_apps(ctx.scope)
        return {"items": [_failed_event(delivery, on) for delivery in page], "total": failed.count()}


def _failed_event(delivery: EventDelivery, on: frozenset[str]) -> dict:
    source = delivery.event.name.split(".", 1)[0]
    return {
        "id": delivery.pk,
        "event_id": delivery.event_id,
        "name": delivery.event.name,
        "source_app": source,
        "source_app_name": system.app_name(source),
        "target_app": delivery.app_label,
        "target_app_name": system.app_name(delivery.app_label),
        "attempts": delivery.attempts,
        "occurred_at": delivery.event.created_at,
        "last_error": delivery.last_error[:FAILED_EVENT_ERROR_LENGTH],
        "retryable": delivery.app_label in on,
    }
