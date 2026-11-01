"""Read operations of base: the session's ``me``, the registry's row of a hub (``base.hub.get``), a demo's status
(``base.demo.get``) and the Home's three live queries (``base.setup.status``, ``base.widget.list``,
``base.bell.counters``; their rules are ``base.home``'s); and Settings › Data's reads (APP-BASE-2): the catalogue of
templates, what a blueprint brings, the export, the loads and the apps' data (their rules are ``base.blueprint``'s)."""

import base64
import csv
import dataclasses
import datetime as dt
import io
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.files.storage import Storage, storages
from django.db.models import Max, Min, Q, Sum
from django.http import HttpRequest
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy, ngettext, pgettext
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound, OperationError, Unauthorized
from live.meta import Category, all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import AI, INTERNAL, operation

from base import access, activation, blueprint, business, entitlement, files, home, meter, system
from base.auth import SAAS_PANEL_PATH, saas_url
from base.models import (
    AccessSettings,
    AppActivation,
    Credential,
    EventDelivery,
    Hub,
    HubUser,
    ImportBatch,
    Membership,
    Profile,
    SessionOwner,
    TrustedDevice,
)
from base.operations import hub_id, is_platform_hub
from base.permissions import ADMINISTER_HUB, FULL_ACCESS_ROLES, VIEW_HOME
from base.registry import hub_answer, internal_only
from base.relay import active_apps
from base.storage import media_url
from base.tenancy import limits as tenancy_limits
from control.models import HubActivityDaily, HubDump, HubUsageDaily, HubVisit, UsageRun
from base.throttle import client_key
from base.schemas import (
    AccessDoorIn,
    AccessDoorOut,
    AccessSettingsIn,
    AccessSettingsOut,
    AppListIn,
    AppListOut,
    DeviceCurrentIn,
    DeviceCurrentOut,
    DeviceByIdIn,
    DeviceListIn,
    DeviceListOut,
    DeviceOut,
    ProfileIn,
    ProfileOut,
    BellCountersIn,
    BellCountersOut,
    BlueprintExportIn,
    BlueprintFileOut,
    BlueprintListIn,
    BlueprintListOut,
    BusinessIn,
    BusinessOut,
    DatasetListIn,
    DatasetListOut,
    ImportIdIn,
    ImportListIn,
    ImportListOut,
    ImportOut,
    DemoSlugIn,
    DemoStatusOut,
    EventListIn,
    EventListOut,
    FailedEventIn,
    FailedEventListIn,
    FailedEventListOut,
    FailedEventOut,
    FileListIn,
    FileListOut,
    FileOut,
    FileReadIn,
    HubGetIn,
    HubUserGetIn,
    HubUserOut,
    HubOut,
    HubsBySlugIn,
    HubsBySlugOut,
    NoticeListIn,
    NoticeListOut,
    HubDumpLinkIn,
    HubDumpLinkOut,
    HubDumpsIn,
    HubDumpsOut,
    InternalDumpsOut,
    PlanUsageIn,
    PlanUsageOut,
    UsageListIn,
    UsageListOut,
    SessionMeIn,
    SessionMeOut,
    SetupStatusIn,
    SetupStatusOut,
    SystemStatusIn,
    SystemStatusOut,
    WidgetListIn,
    WidgetListOut,
)
from base import people as people_rules
from base.schemas import ApiKeyIdIn, ApiKeyListIn, ApiKeyListOut, ApiKeyOut, PersonDetailOut, PersonIn, PersonListIn, PersonListOut, RoleListIn, RoleListOut
from base.models import ApiKey
from live.meta import module_configs
from live.operations import registry as operation_registry


# Not an assistant tool: the SPA's own session, read at start.
@operation("base.session.me", kind="query", permission=None, input=SessionMeIn, output=SessionMeOut, ai=INTERNAL)
def session_me(ctx: OperationContext, data: SessionMeIn) -> dict[str, Any]:
    """The user, its permissions, and the menu and apps it may see on this scope, already translated.

    Menu and apps list modules only (``home.shown_modules``: the reference app only in development, the tests
    or a demo's hub): a platform app such as ``base`` is always on and never shows. A module its business has no
    right to (``base.entitlement``) or turned off (``base.activation``) is ``off`` and has no menu: the shell's gate
    tells why its screens do not open. ``demo`` says when the demo ends, on a demo's hub only. No permission: an anonymous visitor gets ``user: None`` and nothing else, which
    tells the SPA to send it to the login.
    """
    # Labels are lazy translations; a live re-run happens outside the request that activated the
    # language, so it is set here.
    demo = _demo_hub(ctx)
    # Not on: a paid module without its right, or one the business turned off (base.activation); one whose tables the
    # hub's own database is still getting is «activating».
    blocked = entitlement.blocked_apps(ctx.scope) | activation.off_apps(ctx.scope)
    creating = activation.creating_apps(ctx.scope) if blocked else frozenset()
    with translation.override(ctx.language):
        visible = [config for config in home.shown_modules(demo_hub=demo is not None) if _can_see(ctx, config)]
        return {
            "user": _user(ctx.actor, hub_user_of(ctx)),
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
            "apps": [{"label": config.label, "state": _session_state(config.label, blocked, creating)} for config in visible],
            "language": ctx.language,
            "demo": None if demo is None else {"expires_at": demo.expires_at},
        }


def _session_state(label: str, blocked: frozenset[str], creating: frozenset[str]) -> str:
    if label not in blocked:
        return "on"
    return "activating" if label in creating else "off"


def _demo_hub(ctx: OperationContext) -> Hub | None:
    """The demo's hub of this scope (its end, plan 2026-10-17, §1.6, and the reference app it shows), or ``None``
    on a business's hub."""
    if ctx.scope.kind != "host":
        return None
    return Hub.objects.filter(slug=ctx.scope.key, is_demo=True).first()


def _can_see(ctx: OperationContext, config: Any) -> bool:
    return ctx.has(f"{config.label}.view") or any(ctx.has(permission) for permission in config.permissions)


def _user(actor: Any, person: HubUser | None = None) -> dict[str, str] | None:
    if actor is None:
        return None
    if not hasattr(actor, "get_username"):  # the platform itself (live.context.system_context)
        return {"id": str(actor), "label": str(actor)}
    # The person of the business's database (base.HubUser), whose id every app's record names, so a screen tells
    # «mine» by it; without one there yet (the platform's host), the session's user. Named as in this hub: its «My
    # profile» name, else its account's (APP-BASE-3).
    return {"id": str(actor.pk if person is None else person.pk), "label": person_label(actor)}


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.hub.get", kind="query", permission=None, input=HubGetIn, output=HubOut, ai=INTERNAL)
def hub_get(ctx: OperationContext, data: HubGetIn) -> dict[str, Any]:
    """The registry's row of ``data.id`` (``GET /internal/hubs/{id}``), for the platform only: the SaaS asks it about
    a sign-up whose ``ready`` it never heard, and marks it ready when ``status`` is ``ready``."""
    internal_only(ctx)
    hub = Hub.objects.filter(pk=data.id).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    return hub_answer(hub)


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.hub.by_slugs", kind="query", permission=None, input=HubsBySlugIn, output=HubsBySlugOut, ai=INTERNAL)
def hubs_by_slugs(ctx: OperationContext, data: HubsBySlugIn) -> dict[str, Any]:
    """The registry's status of each of ``data.slugs`` (``None`` without a row), in their order, for the platform
    only: ``seed_local_hubs --check`` asks it about ``a`` and ``b``."""
    internal_only(ctx)
    found = dict(Hub.objects.filter(slug__in=data.slugs).values_list("slug", "status"))
    return {"hubs": [{"slug": slug, "status": found.get(slug)} for slug in data.slugs]}


# Not an assistant tool: the SaaS's door to the demo (/internal), no person.
@operation("base.demo.get", kind="query", permission=None, input=DemoSlugIn, output=DemoStatusOut, ai=INTERNAL)
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
    the notices of «Resources» (BASE-F40)."""
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
            notices = _plan_notices(hub)
            if notices:
                counters.insert(
                    0,
                    {
                        "key": "base.plan_limits",
                        "app": "base",
                        "count": notices,
                        "route": "/system#resources",
                        "label": gettext("Plan limits"),
                        "icon": "ion:speedometer-outline",
                    },
                )
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
    """The device's notices (PLAN-HUB round 2026-10-23): the rows the modules on tell, with their texts filled in."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        modules = home.home_modules(active_apps(ctx.scope), demo_hub=bool(hub and hub.is_demo))
        return {"notices": home.device_notices(ctx, modules), "sources": home.notice_sources(ctx, modules)}


# ── Apps (APP-BASE-4) ──────────────────────────────────────────────────────────────────────────────────────────


# Not an assistant tool: the Apps screen's own read; the assistant knows the apps by its catalogue.
@operation("base.app.list", kind="query", permission=VIEW_HOME, input=AppListIn, output=AppListOut, ai=INTERNAL)
def app_list(ctx: OperationContext, data: AppListIn) -> dict:
    """The Apps screen: every module the scope shows, from its own config in this process (PLAN §20.4.1; never the
    SaaS's catalog), with where its right comes from and its state (``base.entitlement``: ``blocked`` without it;
    else ``on`` or ``off`` as the business turned it, ``base.activation``), whether the business chose it, the first
    screen this person may open, what it needs (it comes along with it) and the apps on that need it (they go off
    first); and the plan's limit of chosen apps against the chosen ones on (PLAN-HUB §9), erplora.com's Store and its
    plans of this business.

    Read again when an app's state changes (its live notice, in every process with the list open: AppsFollower on every
    screen), it first forgets what this process kept of the business's apps (``base.activation.forget``): a change the
    worker made in another process (S3) never reaches a cache of the process's own (local development, without
    Valkey), and the session read right after it (the menu) is then current. Transitional: it goes once every process
    hears ``cache_inval '<hex>:apps'`` itself (PLAN-DB §7; FIX-HUB-CACHE-INVAL-APPS-LISTEN)."""
    activation.forget(ctx.scope.key)
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    demo = bool(hub and hub.is_demo)
    configs = home.shown_modules(demo_hub=demo)
    shown = {config.label for config in configs}
    blocked = entitlement.blocked_apps(ctx.scope)
    rights = entitlement.entitlements(None if hub is None or hub.is_demo else hub.state, now=timezone.now())
    graph = activation.module_graph()
    current = activation.states_of(ctx.scope)
    needs = {config.label: entitlement.requires_of(config.label) for config in configs}

    def state(label: str) -> str:
        if label in blocked:
            return "blocked"
        return current[label].state if current[label].wanted else "off"

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
                    "right": entitlement.FREE if demo else rights[config.label],
                    "state": state(config.label),
                    "chosen": current[config.label].wanted and current[config.label].chosen,
                    "path": _first_screen(ctx, config) if state(config.label) == "on" else None,
                    "requires": sorted(needs[config.label]),
                    "required_by": [
                        label for label in activation.required_by(config.label, current, graph) if label in shown
                    ],
                }
                for config in configs
            ],
            "store_url": saas_url(f"{SAAS_PANEL_PATH}/store/modules?business={hub.id}") if hub is not None else "",
            "plan_url": saas_url(f"{SAAS_PANEL_PATH}/store/plans?business={hub.id}") if hub is not None and not demo else "",
            "max_apps": app_limit(hub),
            "enabled": activation.chosen_on(current, among=shown),
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
    """The apps of ``host``'s business whose tables the worker makes now (S3), with the last migration the code that
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


#: From here on the space for files is «Close to the limit»: the same number as erplora.com's panel
#: (``STORAGE_WARNING_PERCENT``), so both say the same of the same figure.
FILES_NEAR_PERCENT = 80
#: Who counts as active now, among all the tasks; a window of activity, not presence (PLAN-HUB §66).
ACTIVE_NOW = dt.timedelta(minutes=5)
#: The days the requests with no room are told for: today and the 6 before it.
BUSY_WINDOW_DAYS = 7


@operation(
    "base.plan.usage",
    kind="query",
    permission=ADMINISTER_HUB,
    input=PlanUsageIn,
    output=PlanUsageOut,
    ai=AI(
        description=(
            "Reads how much this business is using: the space its files take up against what its plan includes, what "
            "it does at once in its database against what it really has and the requests that found no room in the "
            "last 7 days, the requests served this month, the people active now, on the last day measured and in 30 "
            "days, the size of its database, and the people and devices of the plan. A figure that is null has not "
            "been measured yet: say so, never read it as a zero. Files and the database are measured every night."
        ),
        asks={
            "en": (
                "how much space do I have left?",
                "how many requests have we had this month?",
                "how many people are active now?",
                "does my plan fall short?",
            ),
            "es": (
                "¿cuánto espacio me queda?",
                "¿cuántas peticiones llevamos este mes?",
                "¿cuántas personas hay activas ahora?",
                "¿se me queda corto el plan?",
            ),
        },
    ),
)
def plan_usage(ctx: OperationContext, data: PlanUsageIn) -> dict:
    """What «Plan and limits» (BASE-G81) and «Resources» (BASE-F40) of System say: the limits of the plan the SaaS's last
    photo carries (``plan``: ``max_users``, ``max_devices``; 0 = no limit) against the people of the business (its active
    members, the ones the SaaS counts) and the devices in use (those with a session open on this hub: the ones the cap of
    BASE-G57 keeps, APP-BASE-3); what the last night measured (``database``, ``files``, the people of ``activity``); and
    what is counted during the day (``base.meter``: ``connections``, ``requests``, who is active now), as control has it
    plus what this process has not written yet. Memory and CPU cannot be attributed to a business. For who runs the
    business."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    state, plan, known = _plan_of(hub)
    people = Membership.objects.filter(host=ctx.scope.key, user__is_active=True).count()
    devices = (
        SessionOwner.objects.filter(host=ctx.scope.key, session__expire_date__gt=timezone.now())
        .exclude(device_id=None)
        .values("device_id")
        .distinct()
        .count()
    )
    demo = hub is not None and hub.is_demo
    last = None if demo else _last_night(hub)
    counted = _counted_during_the_day(hub) if hub is not None and not demo else _NOTHING_COUNTED
    return {
        "known": known,
        "demo": demo,
        "people": {"used": people, "limit": _limit(plan, "max_users") if known else None},
        "devices": {"used": devices, "limit": _limit(plan, "max_devices") if known else None},
        "database": _database_usage(hub, last),
        "files": _files_usage(state, known, last),
        "connections": _connections_usage(state, known, counted),
        "requests": {"this_month": counted.requests_this_month, "since": counted.requests_since},
        "activity": _activity_usage(hub, demo, last, counted),
    }


def _plan_of(hub: Hub | None) -> tuple[dict, dict | None, bool]:
    """The hub's photo, the plan in it and whether that plan can be read."""
    state = hub.state if hub is not None and isinstance(hub.state, dict) else {}
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else None
    return state, plan, plan is not None and all(_is_count(plan.get(field)) for field in ("max_users", "max_devices"))


def _last_night(hub: Hub | None) -> HubUsageDaily | None:
    """What the last night measured of a hub with its own database (``base.usage``)."""
    if hub is None or not hub.db_name:
        return None
    return HubUsageDaily.objects.filter(hub=hub).order_by("-day").first()


def _database_usage(hub: Hub | None, last: HubUsageDaily | None) -> dict:
    """The size of the business's own database the last night measured (``base.usage``, BASE-F40); none while it shares
    control's (PLAN-DB §14.14: never control's size)."""
    if hub is None or not hub.db_name:
        return {"available": False, "bytes": None, "day": None}
    return {"available": True, "bytes": last.db_bytes if last else None, "day": last.day if last else None}


def _files_usage(state: dict, known: bool, last: HubUsageDaily | None) -> dict:
    """What the files take up (``s3_bytes``) against the plan's space (BASE-F40, step 3); nothing to compare, no status."""
    limit = files.space_limit(state) if known else None
    used = last.s3_bytes if last else None
    percent = status = None
    if limit is not None and used is not None:
        percent = used * 100 // limit
        status = "full" if used >= limit else "near" if used * 100 >= limit * FILES_NEAR_PERCENT else "within"
    return {"bytes": used, "day": last.day if last else None, "limit": limit, "percent": percent, "status": status}


@dataclasses.dataclass(frozen=True)
class _Counted:
    """What was counted of a hub during the days (``base.meter``): nothing is ``None``, never a made-up zero."""

    requests_this_month: int | None = None
    requests_since: dt.date | None = None
    peak_today: int | None = None
    busy_last_7_days: int | None = None
    busy_since: dt.date | None = None
    people_now: frozenset[str] = frozenset()


_NOTHING_COUNTED = _Counted()


def _counted_during_the_day(hub: Hub) -> _Counted:
    """What control holds of the hub's days (one query, by its one index) plus what this process has not written yet. A
    count that started after the first day of its period says since when."""
    today = timezone.now().astimezone(dt.UTC).date()
    month_starts = today.replace(day=1)
    week_starts = today - dt.timedelta(days=BUSY_WINDOW_DAYS - 1)
    kept = HubActivityDaily.objects.filter(hub=hub).aggregate(
        first=Min("day"),
        requests=Sum("requests", filter=Q(day__gte=month_starts)),
        busy=Sum("busy_requests", filter=Q(day__gte=week_starts)),
        peak=Max("peak_connections", filter=Q(day=today)),
    )
    pending = meter.unflushed(hub.pk, hub.slug)
    first = kept["first"] or (today if pending != meter.Unflushed() else None)
    return _Counted(
        requests_this_month=None if first is None else (kept["requests"] or 0) + pending.requests,
        requests_since=first if first is not None and first > month_starts else None,
        # A row with no transaction yet is no measure either: a zero here would be a made-up one.
        peak_today=max(kept["peak"] or 0, pending.peak) or None,
        busy_last_7_days=None if first is None else (kept["busy"] or 0) + pending.busy,
        busy_since=first if first is not None and first > week_starts else None,
        people_now=pending.people,
    )


def _connections_usage(state: dict, known: bool, counted: _Counted) -> dict:
    """Today's highest against what it really has (BASE-F40, step 2). Close to the limit only with a request that found no
    room: with limits of 1, 3 or 6 a percentage says nothing, a Free plan's first operation of the day is its 100 %."""
    limits = tenancy_limits.plan_limits(state) if known else None
    return {
        "peak_today": counted.peak_today,
        "limit": limits.max_transactions if limits else None,
        "busy_last_7_days": counted.busy_last_7_days,
        "busy_since": counted.busy_since,
        "status": ("near" if counted.busy_last_7_days else "within") if limits else None,
        "bigger_plan_gives_more": tenancy_limits.bigger_plan_gives_more(state) if known else False,
    }


def _activity_usage(hub: Hub | None, demo: bool, last: HubUsageDaily | None, counted: _Counted) -> dict:
    """Who is active now, in the last visits of every task (yesterday's too: a day may have just changed) and in this
    process's memory, and the people of the last night measured."""
    now = timezone.now().astimezone(dt.UTC)
    today = now.date()
    active_now = None
    if hub is not None and not demo:
        recent = HubVisit.objects.filter(
            host=hub.slug,
            day__in=(today, today - dt.timedelta(days=1)),
            last_seen_at__gte=now - ACTIVE_NOW,
        ).values_list("saas_user_id", flat=True)
        active_now = len(set(recent) | counted.people_now)
    return {
        "active_now": active_now,
        "last_day": last.active_users_1d if last else None,
        "last_day_date": last.day if last else None,
        "last_day_is_yesterday": last is not None and last.day == today - dt.timedelta(days=1),
        "last_30_days": last.active_users_30d if last else None,
    }


def _plan_notices(hub: Hub | None) -> int:
    """How many notices «Resources» shows (BASE-F40, steps 5, 6 and 8): the one of the files and the one of the
    connections, read as the screen reads them; none without the plan or in a demo."""
    state, _, known = _plan_of(hub)
    if not known or hub is None or hub.is_demo:
        return 0
    files_status = _files_usage(state, known, _last_night(hub))["status"]
    connections_status = _connections_usage(state, known, _counted_during_the_day(hub))["status"]
    return int(files_status in ("near", "full")) + int(connections_status == "near")


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation("base.usage.list", kind="query", permission=None, input=UsageListIn, output=UsageListOut, ai=INTERNAL)
def usage_list(ctx: OperationContext, data: UsageListIn) -> dict[str, Any]:
    """One page of what the hubs with their own database used on ``data.day`` (``GET /internal/usage``, the SaaS's
    ``collect_hub_usage``), by hub id, after ``data.cursor``; 409 ``usage_not_ready`` until that night was measured to
    its end (``base.usage``). For the platform only."""
    from base import usage

    internal_only(ctx)
    if not UsageRun.objects.filter(day=data.day, finished_at__isnull=False).exists():
        raise OperationError(gettext("That day has not been measured yet."), code="usage_not_ready", status=409)
    rows = HubUsageDaily.objects.filter(day=data.day).order_by("hub_id")
    if data.cursor is not None:
        rows = rows.filter(hub_id__gt=data.cursor)
    page = list(rows[: usage.PAGE_SIZE + 1])
    more = len(page) > usage.PAGE_SIZE
    page = page[: usage.PAGE_SIZE]
    activity = {
        row.hub_id: row
        for row in HubActivityDaily.objects.filter(day=data.day, hub_id__in=[row.hub_id for row in page])
    }
    return {
        "day": data.day,
        "hubs": [
            {
                "id": row.hub_id,
                "s3_bytes": row.s3_bytes,
                "db_bytes": row.db_bytes,
                "active_users_1d": row.active_users_1d,
                "active_users_30d": row.active_users_30d,
                "requests": activity[row.hub_id].requests if row.hub_id in activity else None,
                "peak_connections": activity[row.hub_id].peak_connections if row.hub_id in activity else None,
                "busy_requests": activity[row.hub_id].busy_requests if row.hub_id in activity else None,
            }
            for row in page
        ],
        "next_cursor": str(page[-1].hub_id) if more else None,
    }


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _limit(plan: dict, field: str) -> int | None:
    """A limit of the plan; 0 is none."""
    return plan[field] or None


# ── Data: blueprints, imports and reset (APP-BASE-2) ──
#: The loads Settings › Data lists: the latest ones.
IMPORTS_SHOWN = 50


@operation(
    "base.blueprint.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=BlueprintListIn,
    output=BlueprintListOut,
    ai=AI(
        description=(
            "Lists the templates of businesses this hub can load (a restaurant, a hair salon…): what each one brings "
            "(its apps, its menu or services, its tables) and whether this business is still empty."
        ),
        asks={
            "en": (
                "which templates can I start from?",
                "show me the business templates",
                "is there a template for a bakery?",
            ),
            "es": (
                "¿qué plantillas hay?",
                "¿tenéis alguna plantilla para una panadería?",
                "enséñame los modelos de negocio para empezar",
            ),
        },
    ),
)
def blueprint_list(ctx: OperationContext, data: BlueprintListIn) -> dict:
    """The seeds by vertical (BASE-G103): the hub's country first, then the person's language, then the hub's vertical."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        country, vertical = (hub.country, hub.vertical) if hub else ("", "")
        seeds = sorted(
            blueprint.catalog(),
            key=lambda seed: (
                bool(country) and seed.country != country,
                seed.language != ctx.language,
                bool(vertical) and seed.vertical != vertical,
                seed.key,
            ),
        )
        return {"templates": [blueprint.template_out(seed) for seed in seeds], "empty": blueprint.no_rows_yet(ctx)}


@operation(
    "base.blueprint.export",
    kind="query",
    permission=ADMINISTER_HUB,
    input=BlueprintExportIn,
    output=BlueprintFileOut,
    ai=AI(
        description=(
            "Writes a .blueprint.zip of this business: the apps chosen and, of those marked, their data. A template "
            "never takes personal data (customers); a backup takes them. People, PINs and fiscal data never."
        ),
        risk="high",
        # Only for live.E020 (it checks the whole app): base.assistant.NOT_FROM_CHAT keeps this out of the chat
        # (pinned by base/tests/test_assistant.py).
        asks={
            "en": ("make a backup of the whole business", "export my menu as a template for the other bar"),
            "es": ("haz una copia de seguridad del negocio", "exporta mi carta como plantilla para el otro local"),
        },
    ),
)
def blueprint_export(ctx: OperationContext, data: BlueprintExportIn) -> dict:
    """The file of the apps and datasets chosen (BASE-G101, BASE-G102), in base64 for the screen to save."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        on = blueprint.active_apps(ctx.scope)
        shown = {config.label for config in home.shown_modules(demo_hub=bool(hub and hub.is_demo))}
        registered = list(dict.fromkeys(data.apps))
        missing = [app for app in registered if app not in shown or app not in on]
        if missing:
            raise InvalidPayload(
                gettext("The app «%(app)s» is not on in this business.") % {"app": missing[0]},
                fields={"apps": gettext("Choose only apps that are on in this business.")},
            )
        if not set(data.data) <= set(registered):
            raise InvalidPayload(
                gettext("The data of an app travels only with the app."),
                fields={"data": gettext("Mark the app too, not only its data.")},
            )
        named = set(data.datasets)
        own = {app: [part.key for part in blueprint.datasets_of(app)] for app in dict.fromkeys(data.data)}
        if not named <= {key for keys in own.values() for key in keys}:
            raise InvalidPayload(
                gettext("Some of the data chosen belongs to no app whose data travels."),
                fields={"datasets": gettext("Choose only data of the app it belongs to.")},
            )
        chosen = {app: [key for key in keys if key in named] or keys for app, keys in own.items()}
        bundle = blueprint.Bundle(
            manifest=blueprint.manifest(
                name=data.name.strip(),
                language=data.language,
                country=hub.country if hub else "",
                purpose=data.purpose,
                created_at=timezone.now().isoformat(),
                vertical=hub.vertical if hub else "",
                apps=registered,
            ),
            data=blueprint.export_data(ctx, chosen, purpose=data.purpose),
        )
        # INVENTORY-F33: the rows' own photos travel inside the file; the library's images by their reference.
        bundle.media = blueprint.export_media(ctx, bundle.data)
        return {
            "filename": blueprint.file_name(data.name, data.language),
            "content_type": "application/zip",
            "content_base64": base64.b64encode(blueprint.write_zip(bundle)).decode("ascii"),
        }


# ── The copies of the business's data (round 2026-10-30 of PLAN-DB, decision 2, proposals (k), (l)) ───────────────


def _dumps_unavailable() -> OperationError:
    return OperationError(
        gettext("The copy cannot be downloaded right now. Try again in a moment."),
        code="base.dumps_unavailable",
        status=503,
    )


def _reset_state(hub: Hub) -> dict | None:
    """The last reset of ``hub`` as Settings › Data shows it (``Hub.reset_sections``), or ``None`` before the first."""
    asked = hub.reset_sections if isinstance(hub.reset_sections, dict) else None
    if not asked or asked.get("state") not in ("copying", "emptying", "done", "failed"):
        return None
    return {
        "state": asked["state"],
        "sections": [{"id": app, "label": blueprint.app_label(app)} for app in asked.get("apps") or []],
        "requested_by": asked.get("requested_by") or "",
        "error": asked.get("error") or "",
        "removed": asked.get("removed") or [],
        "finished_at": asked.get("finished_at"),
    }


def _kept_dumps(hub: Hub):
    """The copies of ``hub`` still in the bucket, newest first: none past its 90 days (``dumps.RETENTION``), which the
    bucket's lifecycle rule deleted or is about to."""
    from base.tenancy import dumps

    return HubDump.objects.filter(hub=hub, created_at__gt=timezone.now() - dumps.RETENTION).order_by("-created_at", "-id")


def gets_copies(hub: Hub) -> bool:
    """Whether ``hub`` has, or will have, copies of its data: its own database, made (or being made); never a business
    that shares control's, nor one that left before its database was finished."""
    from base import registry

    return bool(hub.db_name) and (hub.ready_at is not None or hub.status in registry.PREPARING_STATUSES)


@operation(
    "base.hub.dumps",
    kind="query",
    permission=ADMINISTER_HUB,
    input=HubDumpsIn,
    output=HubDumpsOut,
    ai=AI(
        description=(
            "Lists the full copies of this business's data that ERPlora keeps for 90 days (one before each reset, one "
            "when the business is deleted): when each was made and how big it is, newest first; and how the last "
            "reset of the business went (copying, emptying, done or failed, and what was removed)."
        ),
        asks={
            "en": ("do I have a backup of my data?", "show me the copies of my data made before the reset"),
            "es": ("¿tengo una copia de seguridad de mis datos?", "¿cómo fue el restablecimiento del negocio?"),
        },
    ),
)
def hub_dumps(ctx: OperationContext, data: HubDumpsIn) -> dict:
    """Settings › Data's «Copies» (BASE-F37): the copies of the business's own database, without their links
    (``base.hub.dump_link`` gives one on each click), and how its last reset went (``base.services``, «The reset of a
    business»). While the business shares its database with others, nothing (PLAN-DB §14.14)."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        if hub is None or not hub.db_name:
            return {"available": False, "reset": None, "dumps": []}
        return {
            "available": True,
            "reset": _reset_state(hub),
            "dumps": [
                {"id": dump.pk, "kind": dump.kind, "created_at": dump.created_at, "bytes": dump.bytes}
                for dump in _kept_dumps(hub)
            ],
        }


# Not an assistant tool: a link that downloads every person's data of the business is for the person on the screen.
@operation(
    "base.hub.dump_link",
    kind="query",
    permission=ADMINISTER_HUB,
    input=HubDumpLinkIn,
    output=HubDumpLinkOut,
    ai=INTERNAL,
)
def hub_dump_link(ctx: OperationContext, data: HubDumpLinkIn) -> dict:
    """The link of one copy of the business's data, signed for 15 minutes when it is asked (each «Download»); a copy of
    another business is not found."""
    from base.tenancy import dumps

    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        dump = _kept_dumps(hub).filter(pk=data.id).first() if hub is not None and hub.db_name else None
        if dump is None:
            raise NotFound(gettext("This copy is no longer kept."))
        try:
            url = dumps.presigned_url(dump.key, filename=dumps.file_name(hub.slug, dump.key))
        except dumps.DumpsUnavailable:
            raise _dumps_unavailable() from None
        return {"url": url, "expires_at": dumps.link_expires_at(url)}


# Not an assistant tool: the platform's door (/internal, the SaaS), no person.
@operation(
    "base.hub.dump_list", kind="query", permission=None, input=HubGetIn, output=InternalDumpsOut, ai=INTERNAL
)
def hub_dump_list(ctx: OperationContext, data: HubGetIn) -> dict:
    """The copies of ``data.id``'s data (``GET /internal/hubs/{id}/dumps``, the SaaS's panel and its mails of a
    deletion), newest first, each with a link of 15 minutes; ``available`` false for a business that never gets one.
    A business that left answers too (the 410 is its host's door); one unknown or purged is not found."""
    from base.tenancy import dumps

    internal_only(ctx)
    hub = Hub.objects.filter(pk=data.id).exclude(status=Hub.Status.PURGED).first()
    if hub is None:
        raise NotFound(gettext("No hub has this id."))
    if not gets_copies(hub):
        return {"available": False, "dumps": []}
    if not dumps.configured():
        # No bucket: this Hub can make no copy, so «none yet» would promise one (PLAN-SAAS §24: a failure, not «none»).
        raise _dumps_unavailable()
    rows = list(_kept_dumps(hub))
    try:
        listed = [
            {
                "id": dump.key,
                "kind": dump.kind,
                "created_at": dump.created_at,
                "bytes": dump.bytes,
                "url": dumps.presigned_url(dump.key, filename=dumps.file_name(hub.slug, dump.key)),
            }
            for dump in rows
        ]
    except dumps.DumpsUnavailable:
        raise _dumps_unavailable() from None
    return {"available": True, "dumps": listed}


@operation(
    "base.import.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ImportListIn,
    output=ImportListOut,
    ai=AI(
        description=(
            "Lists the templates and files loaded into this business, newest first, each with its report, whether it "
            "can be undone and whether what did not go in can be loaded again."
        ),
        asks={
            "en": ("what have we imported so far?", "list the templates we loaded"),
            "es": ("¿qué importaciones hemos hecho?", "lista las plantillas que hemos cargado"),
        },
    ),
)
def import_list(ctx: OperationContext, data: ImportListIn) -> dict:
    """The loads, newest first; the last one, when it did not go in whole and stands, is shown first (BASE-G107)."""
    loads = list(ImportBatch.objects.order_by("-created_at", "-id")[:IMPORTS_SHOWN])
    latest = loads[0] if loads else None
    unfinished = latest if latest and latest.status != ImportBatch.Status.COMPLETE and latest.undone_at is None else None
    return {
        "imports": [blueprint.describe_load(load) for load in loads],
        "unfinished": blueprint.describe_load(unfinished) if unfinished else None,
    }


@operation(
    "base.import.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ImportIdIn,
    output=ImportOut,
    ai=AI(
        description="Reads one template or file loaded into this business, by its id, as the list of loads shows it.",
        asks={
            "en": ("what did that template load bring in?", "show me the report of yesterday's import"),
            "es": ("¿qué metió esa carga de plantilla?", "enséñame el informe de la importación de ayer"),
        },
    ),
)
def import_detail(ctx: OperationContext, data: ImportIdIn) -> dict:
    """One load of Settings › Data (BASE-G107), as its row."""
    load = ImportBatch.objects.filter(pk=data.id).first()
    if load is None:
        raise NotFound(gettext("This load is not there any more."))
    return blueprint.describe_load(load)


@operation(
    "base.dataset.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=DatasetListIn,
    output=DatasetListOut,
    ai=AI(
        description=(
            "Lists the apps on in this business and, of each, what can travel in an export and how many rows it has."
        ),
        asks={
            "en": ("what data can I export?", "how many rows does each app have?"),
            "es": ("¿cuántos registros tiene cada app?", "¿qué se puede sacar en una exportación?"),
        },
    ),
)
def dataset_list(ctx: OperationContext, data: DatasetListIn) -> dict:
    """Every app on (BASE-G102), with its datasets and their rows: what an export can take."""
    with translation.override(ctx.language):
        hub = Hub.objects.filter(slug=ctx.scope.key).first()
        on = blueprint.active_apps(ctx.scope)
        counts = blueprint.counts(ctx)
        apps = [
            {
                "id": config.label,
                "label": str(config.verbose_name),
                "icon": config.icon,
                "datasets": [
                    {"key": part.key, "label": str(part.label), "rows": counts.get(part.key, 0), "personal": part.personal}
                    for part in blueprint.datasets_of(config.label)
                ],
            }
            for config in home.shown_modules(demo_hub=bool(hub and hub.is_demo))
            if config.label in on
        ]
        return {"apps": sorted(apps, key=lambda app: app["label"])}


# ── Business settings and the hub's context (APP-BASE-6) ──


@operation(
    "base.business.get",
    kind="query",
    permission=VIEW_HOME,
    input=BusinessIn,
    output=BusinessOut,
    ai=AI(
        description=(
            "Reads this business's name, country, time zone, language and currency, as erplora.com registered it. They "
            "are changed on erplora.com by the owner or an administrator, never here; the country no longer changes "
            "once the business is ready, and the currency is always the country's."
        ),
        asks={
            "en": (
                "what currency is the business in?",
                "what's our time zone?",
                "under what name is the business registered?",
            ),
            "es": (
                "¿en qué moneda trabaja el negocio?",
                "¿qué zona horaria tenemos?",
                "¿con qué nombre está dado de alta el negocio?",
            ),
        },
    ),
)
def business_get(ctx: OperationContext, data: BusinessIn) -> dict:
    """Settings › Business (BASE-G97…G99) and what the old ``/api/hub/context`` gave (BASE-G43): the business as the
    SaaS registered it, from the registry of this scope, never another's. The currency is its country's
    (``base.business``); a demo has no business on erplora.com, hence no address to change it, and the deployment's
    zone and language until the SaaS says otherwise. ERPlora's own hub (PLAN-SAAS §4) is ERPlora itself, the issuer of
    its invoices: its legal name and country from ``PLATFORM_ISSUER_*``, row or not (phase 1 has none,
    ``create_platform_hub``), so its currency is the one its invoices and its apps charge in; nothing of it is changed
    on erplora.com. Every app asks for that currency through ``base.operations.business_currency``."""
    if is_platform_hub(ctx.scope):
        return _business(
            ctx,
            name=settings.PLATFORM_ISSUER_LEGAL_NAME,
            country=settings.PLATFORM_ISSUER_COUNTRY,
            zone=settings.TIME_ZONE,
            language=settings.LANGUAGE_CODE,
            demo=False,
            settings_url="",
        )
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    if hub is None:
        raise NotFound(gettext("There is no business here."))
    return _business(
        ctx,
        name=hub.name,
        country=hub.country,
        zone=hub.timezone or settings.TIME_ZONE,
        language=hub.language or settings.LANGUAGE_CODE,
        demo=hub.is_demo,
        settings_url="" if hub.is_demo else saas_url(f"{SAAS_PANEL_PATH}/businesses/{hub.id}/settings"),
    )


def _business(
    ctx: OperationContext, *, name: str, country: str, zone: str, language: str, demo: bool, settings_url: str
) -> dict:
    """``BusinessOut`` of one business, each value named in ``ctx``'s language."""
    currency = business.currency_of(country)
    return {
        "name": name,
        "country": country,
        "country_name": business.country_name(country, ctx.language),
        "timezone": zone,
        "language": language,
        "language_name": business.language_name(language, ctx.language),
        "currency": currency,
        "currency_label": business.currency_label(currency, ctx.language),
        "currency_decimals": business.currency_decimals(currency),
        "demo": demo,
        "settings_url": settings_url,
    }


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
    ai=AI(
        description=(
            "Reads the status of this hub's system: the version of ERPlora it runs and when that version was published "
            "(the hub updates itself, nobody installs anything), and whether its data is on the database every "
            "business shares or on its own."
        ),
        asks={
            "en": ("which ERPlora version are we on?", "is the system up to date?"),
            "es": ("¿qué versión de ERPlora tenemos?", "¿está actualizado el sistema?"),
        },
    ),
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
    ai=AI(
        description=(
            "Reads the log of the last 50 events between this hub's apps (a sale charged, a round fired…), newest "
            "first: when each happened, which app recorded it, its level (info, warning, error) and what happened to "
            "it (delivered to each app, retrying, given up and waiting in «Failed events», discarded). Never the "
            "content of an event."
        ),
        asks={
            "en": ("what's been happening between the apps?", "show me the latest event log"),
            "es": ("enséñame el registro de eventos", "¿qué ha pasado entre las apps últimamente?"),
        },
    ),
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
    ai=AI(
        description=(
            "Lists the failed events of this hub, newest first: messages between apps (a sale to Invoicing, a round to "
            "Printing…) that could not be delivered after every retry. Each one says the event, the app that sent it "
            "and the one that could not take it, the attempts, when it happened, the start of the last error and "
            "whether it can be resent (not when the app it was for is no longer on). Pages of up to 100."
        ),
        asks={
            "en": (
                "is anything stuck between the apps?",
                "list the failed events",
                "what never got delivered to printing?",
            ),
            "es": ("¿hay algo atascado entre las apps?", "lista los eventos caídos"),
        },
    ),
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


@operation(
    "base.failed_event.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=FailedEventIn,
    output=FailedEventOut,
    ai=AI(
        description=(
            "Reads one failed event of this hub by its id, as the list of failed events shows it: the event, the app "
            "that sent it and the one that could not take it, the attempts and whether it can be resent."
        ),
        asks={
            "en": ("why did that failed event fail?", "show me the failed invoicing event"),
            "es": ("¿por qué ha fallado ese evento?", "dame el detalle del evento caído de facturación"),
        },
    ),
)
def failed_event_detail(ctx: OperationContext, data: FailedEventIn) -> dict:
    """One failed event of System (a delivery the relay gave up on), of the hub of ``ctx`` only."""
    delivery = (
        EventDelivery.objects.select_related("event")
        .filter(
            pk=data.id,
            status=EventDelivery.Status.DEAD,
            event__scope_kind=ctx.scope.kind,
            event__scope_key=ctx.scope.key,
        )
        .first()
    )
    if delivery is None:
        raise NotFound(gettext("That failed event is no longer in the queue: refresh the list."))
    with translation.override(ctx.language):
        return _failed_event(delivery, active_apps(ctx.scope))


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


# ── The way in: devices, PIN, badge, the business's dial and the person's profile (APP-BASE-3) ───────────────────


def access_settings() -> AccessSettings:
    """How the business asks who is at the till: its row, or the factory values (an unsaved row) without one. A
    stored value this build does not understand reads as the factory one, never as «not asking» (``base.access``)."""
    row = AccessSettings.objects.first() or AccessSettings()
    row.pin_policy = access.policy_or_default(row.pin_policy)
    row.pin_inactivity_minutes = access.inactivity_or_default(row.pin_inactivity_minutes)
    row.pin_length = access.pin_length_or_default(row.pin_length)
    return row


def person_label(user) -> str:
    """How ``user`` is named in this hub: its «My profile» name, else its erplora.com account's, else its username."""
    profile = Profile.objects.filter(username=user.get_username()).only("first_name", "last_name").first()
    if profile is not None and (name := f"{profile.first_name} {profile.last_name}".strip()):
        return name
    return user.get_full_name() or user.get_username()


def face_name(user) -> str:
    """How ``user`` shows on the grid of a till (BASE-G55, G60), seen by anyone at it: their name, never an email (the
    SaaS names an account without a name by its address: then the part before the «@»; gh:hub#2536)."""
    label = person_label(user)
    return label.split("@", 1)[0] if "@" in label else label


def device_of(request: HttpRequest | None, *, for_update: bool = False) -> TrustedDevice | None:
    """The hub's device this browser's cookie names, or ``None`` (no request or cookie, or a device the hub does not
    know: never one in which nobody entered with an account, nor one that was removed)."""
    token = request.COOKIES.get(access.DEVICE_COOKIE, "") if request is not None else ""
    if not token:
        return None
    devices = TrustedDevice.objects.select_for_update() if for_update else TrustedDevice.objects
    return devices.filter(token_digest=access.token_digest(token)).first()


def pin_people(slug: str, *, exclude: str = "") -> list[tuple[Credential, Any]]:
    """The active people of ``slug`` with a PIN, with their user (but ``exclude``, a username); in no order.

    Two reads, never a join: who is a member is control's (``Membership``) and the PINs are the hub's."""
    users = {
        membership.user.get_username(): membership.user
        for membership in Membership.objects.filter(host=slug, user__is_active=True).select_related("user")
    }
    users.pop(exclude, None)
    credentials = Credential.objects.filter(username__in=list(users)).exclude(pin_hash="")
    return [(credential, users[credential.username]) for credential in credentials]


def pin_owner(slug: str, person: str, pin: str) -> Any | None:
    """The active person of ``slug`` whose way in is ``person`` and whose PIN is ``pin``; else ``None``, whatever
    failed (an unknown id, another hub's person, a deactivated one, no PIN, a wrong one: the door says the same)."""
    try:
        person_id = UUID(person)
    except (TypeError, ValueError):
        return None
    credential = Credential.objects.filter(pk=person_id).exclude(pin_hash="").first()
    if credential is None:
        return None
    membership = (
        Membership.objects.filter(host=slug, user__username=credential.username, user__is_active=True)
        .select_related("user")
        .first()
    )
    if membership is None or not check_password(pin, credential.pin_hash):
        return None
    return membership.user


def pin_door_open(request: HttpRequest, slug: str) -> bool:
    """Whether this browser enters ``slug`` by the PIN pad: a shared device of the hub, a business that asks, and
    somebody of it with a PIN to choose."""
    device = device_of(request)
    if device is None or not access.pin_offered(device.mode, access_settings().pin_policy):
        return False
    return bool(pin_people(slug))


@operation(
    "base.access.door",
    kind="query",
    permission=None,
    input=AccessDoorIn,
    output=AccessDoorOut,
    ai={
        "description": "Not an assistant tool (what the browser of a till shows by itself, before anyone is in): the "
        "people who can enter with a PIN on this shared device, by name and initials, and the PIN's length."
    },
)
def access_door(ctx: OperationContext, data: AccessDoorIn) -> dict[str, Any]:
    """The way in of the browser that asks (BASE-G55): on a shared device of the hub of a business that asks, the
    people of this hub with a PIN, by name and initials (never their email nor account) and the PIN's length.

    The grid reaches only whom the PIN would let in (the old Hub's HUB-F133): anyone else, and an address that tried
    too many wrong PINs (with how long it still waits), hears the same answer with nobody in it."""
    return _door(ctx)


@operation(
    "base.access.faces",
    kind="query",
    permission=VIEW_HOME,
    input=AccessDoorIn,
    output=AccessDoorOut,
    ai={
        "description": "Not an assistant tool (the «Switch user» grid of the till in hand, followed live): the people "
        "who can enter with a PIN on this device, by name and initials."
    },
)
def access_faces(ctx: OperationContext, data: AccessDoorIn) -> dict[str, Any]:
    """The door's grid for a session: «Switch user» (BASE-G60), live, so a new PIN shows up and a person removed
    leaves without reloading the till."""
    return _door(ctx)


def _door(ctx: OperationContext) -> dict[str, Any]:
    settings = access_settings()
    device = device_of(ctx.request)
    offered = device is not None and access.pin_offered(device.mode, settings.pin_policy)
    wait = access.PIN_ADDRESS_LIMIT.wait(ctx.scope.key, client_key(ctx.request)) if offered else 0
    people = [] if not offered or wait else pin_people(ctx.scope.key)
    faces = sorted(
        ({"id": str(credential.pk), "name": (name := face_name(user)), "initials": access.initials(name)}
         for credential, user in people),
        key=lambda face: face["name"].casefold(),
    )
    return {
        "pin": offered and (bool(faces) or wait > 0),
        "pin_length": settings.pin_length,
        "people": faces,
        "wait": wait,
        # BASE-G57's «Upgrade plan» to a browser nobody is signed in on: erplora.com's plans, never this hub's id.
        "plan_url": saas_url(f"{SAAS_PANEL_PATH}/store/plans"),
    }


def chosen_language(user) -> str:
    """The language a person chose in «My profile»; empty while it is the business's."""
    return Profile.objects.filter(username=user.get_username()).values_list("language", flat=True).first() or ""


def language_of(user, slug: str) -> str:
    """The language a person works in on ``slug``: their «My profile» choice, else the business's."""
    return chosen_language(user) or Hub.objects.filter(slug=slug).values_list("language", flat=True).first() or ""


def device_of_entry(request: HttpRequest) -> TrustedDevice | None:
    """The device an entry of this request was made on: the token it just left (a new device's) or the cookie's."""
    token = getattr(request, access.DEVICE_TOKEN_ATTR, None)
    if token:
        return TrustedDevice.objects.filter(token_digest=access.token_digest(token)).first()
    return device_of(request)


def has_pin(user) -> bool:
    return Credential.objects.filter(username=user.get_username()).exclude(pin_hash="").exists()


@operation(
    "base.device.current",
    kind="query",
    permission=VIEW_HOME,
    input=DeviceCurrentIn,
    output=DeviceCurrentOut,
    ai=AI(
        description="Says whether the device the person is using is shared (a till: PIN, a shift) or personal.",
        asks={
            "en": ("is this a shared device?", "what mode is this device in?", "does this device ask for a PIN?"),
            "es": ("¿este aparato es de uso compartido?", "¿este dispositivo pide PIN?"),
        },
    ),
)
def device_current(ctx: OperationContext, data: DeviceCurrentIn) -> dict[str, Any]:
    """«This device» of Settings › General (BASE-G72): the mode of the browser that asks, and whether the hub knows it
    (someone entered with an account from it). An unknown one reads as shared, the strict mode."""
    device = device_of(ctx.request)
    if device is None:
        return {"known": False, "mode": access.SHARED, "mode_set_by": "", "mode_set_at": None}
    return {"known": True, "mode": device.mode, "mode_set_by": device.mode_set_by, "mode_set_at": device.mode_set_at}


@operation(
    "base.device.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=DeviceListIn,
    output=DeviceListOut,
    ai=AI(
        description=(
            "Lists the devices someone entered this hub from: name, browser, shared or personal, whether it has a "
            "session open now and until when, who entered last and when, and which ones nobody used in 30 days."
        ),
        asks={
            "en": (
                "which devices are signed in to the business?",
                "list the tablets and computers",
                "which devices haven't been used in a month?",
            ),
            "es": ("lista las tablets y ordenadores del negocio", "¿qué aparatos llevan un mes sin usarse?"),
        },
    ),
)
def device_list(ctx: OperationContext, data: DeviceListIn) -> dict[str, Any]:
    """«Devices» of Settings › General (BASE-G63): never a device's token, which is its proof. Phase 1 lists the rows
    of the shared table (every scope's), as every hub model does until each hub has its database."""
    rows = _device_rows(ctx, list(TrustedDevice.objects.order_by("-last_entry_at")))
    return {"devices": rows, "unused": sum(row["unused"] for row in rows)}


@operation(
    "base.device.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=DeviceByIdIn,
    output=DeviceOut,
    ai=AI(
        description=(
            "Reads one device someone entered this hub from, by its id, as the devices list shows it: its name first."
        ),
        asks={
            "en": ("show me the kitchen tablet's details", "who used the bar device last?"),
            "es": (
                "¿quién entró el último en el dispositivo de la barra?",
                "¿quién usó por última vez el ordenador de la oficina?",
            ),
        },
    ),
)
def device_detail(ctx: OperationContext, data: DeviceByIdIn) -> dict[str, Any]:
    """One device of «Devices» (BASE-G63), as its row: what the assistant's card names a device by."""
    device = TrustedDevice.objects.filter(pk=data.id).first()
    if device is None:
        raise NotFound(gettext("That device is no longer registered here. Refresh the list."))
    return _device_rows(ctx, [device])[0]


def _device_rows(ctx: OperationContext, devices: list[TrustedDevice]) -> list[dict[str, Any]]:
    """``devices`` as «Devices» lists them, with whether each has a session open now and until when."""
    now = timezone.now()
    here = device_of(ctx.request)
    until = dict(
        SessionOwner.objects.filter(host=ctx.scope.key, device_id__in=[d.pk for d in devices], session__expire_date__gt=now)
        .values("device_id")
        .annotate(until=Max("session__expire_date"))
        .values_list("device_id", "until")
    )
    return [
        {
            "id": device.pk,
            "name": device.name,
            "agent": device.agent,
            "mode": device.mode,
            "current": here is not None and device.pk == here.pk,
            "in_use": device.pk in until,
            "session_until": until.get(device.pk),
            "last_entry_at": device.last_entry_at,
            "last_user": device.last_user_label,
            "created_at": device.created_at,
            "unused": _unused(device, here, now),
        }
        for device in devices
    ]


def _unused(device: TrustedDevice, here: TrustedDevice | None, now) -> bool:
    return (here is None or device.pk != here.pk) and device.last_entry_at < now - access.UNUSED_AFTER


def unused_devices(here: TrustedDevice | None):
    """The devices «Remove the unused» removes (BASE-G66): nobody entered on them in 30 days, never the one in hand."""
    old = TrustedDevice.objects.filter(last_entry_at__lt=timezone.now() - access.UNUSED_AFTER)
    return old.exclude(pk=here.pk) if here is not None else old


@operation(
    "base.access.settings",
    kind="query",
    permission=VIEW_HOME,
    input=AccessSettingsIn,
    output=AccessSettingsOut,
    ai=AI(
        description=(
            "Reads how the business asks who is at the till: whether the PIN pad shows, when it asks again (after some "
            "minutes without use, or once per shift) and how many digits a PIN has."
        ),
        asks={
            "en": (
                "how many digits is the PIN?",
                "does the till ask for the PIN again after a while?",
                "when does the screen lock and ask who's there?",
            ),
            "es": (
                "¿cada cuánto pide el PIN la caja?",
                "¿se bloquea la caja si nadie la toca?",
                "¿el PIN es de 4 o de 6 cifras?",
            ),
        },
    ),
)
def access_settings_get(ctx: OperationContext, data: AccessSettingsIn) -> dict[str, Any]:
    """The «PIN pad» card of Settings › General (BASE-G62, G151): what the Hub confirmed, for everyone of the hub."""
    row = access_settings()
    return {
        "pin_policy": row.pin_policy,
        "pin_inactivity_minutes": row.pin_inactivity_minutes,
        "pin_length": row.pin_length,
        "can_change": ctx.has(ADMINISTER_HUB),
    }


@operation(
    "base.profile.get",
    kind="query",
    permission=VIEW_HOME,
    input=ProfileIn,
    output=ProfileOut,
    ai=AI(
        description="Reads the person's own profile in this hub: name, contact email, language and appearance.",
        asks={
            "en": ("what email is on my profile?", "show me my profile"),
            "es": ("¿qué correo tengo en mi perfil?", "¿con qué nombre salgo yo?"),
        },
    ),
)
def profile_get(ctx: OperationContext, data: ProfileIn) -> dict[str, Any]:
    """«My profile» (BASE-G125): always the profile of whoever asks; without a row, the account's name."""
    user = signed_in(ctx)
    profile = Profile.objects.filter(username=user.get_username()).first()
    role = Membership.objects.filter(user=user, host=ctx.scope.key).values_list("role", flat=True).first() or ""
    return {
        "first_name": profile.first_name if profile else user.first_name,
        "last_name": profile.last_name if profile else user.last_name,
        "contact_email": profile.contact_email if profile else "",
        "avatar_url": avatar_url(ctx, profile.avatar) if profile and profile.avatar else "",
        "language": profile.language if profile else "",
        "theme_mode": profile.theme_mode if profile else "",
        "palette": profile.palette if profile else "",
        "role": role,
        "has_pin": has_pin(user),
        "pin_length": access_settings().pin_length,
    }


def signed_in(ctx: OperationContext):
    """The person of the session, or 401: «My profile» and one's own PIN are nobody's without one."""
    if ctx.actor is None or not hasattr(ctx.actor, "get_username"):
        raise Unauthorized(gettext("Sign in to see your profile."), code="base.sign_in_required")
    return ctx.actor


def avatar_url(ctx: OperationContext, name: str) -> str:
    return media_url(hub_id(ctx.scope), name)


def appearance_of(user) -> dict[str, str]:
    """The mode and palette a person chose in «My profile» (BASE-G125), for the shell to paint on any device they enter;
    empty, the business's."""
    chosen = Profile.objects.filter(username=user.get_username()).values("theme_mode", "palette").first()
    return {"theme_mode": chosen["theme_mode"], "palette": chosen["palette"]} if chosen else {"theme_mode": "", "palette": ""}


def shell_access(request: HttpRequest, slug: str) -> dict[str, Any]:
    """What the shell needs of this session's way in (``hub-home``'s ``access``, ``base.spa``): how it was opened,
    whether «Switch user» is offered (BASE-G60: a shared device of the hub of a business that asks, with somebody on
    its grid) and, when the business always asks on such a device, after how many idle minutes it locks (BASE-G59)."""
    credential = (
        SessionOwner.objects.filter(session_id=request.session.session_key).values_list("credential", flat=True).first()
        or SessionOwner.Credential.ACCOUNT
    )
    device = device_of(request)
    settings = access_settings()
    offered = device is not None and access.pin_offered(device.mode, settings.pin_policy)
    return {
        "credential": credential,
        "switch_user": offered and bool(pin_people(slug)),
        "idle_minutes": settings.pin_inactivity_minutes if offered and settings.pin_policy == access.ALWAYS else None,
    }


# ── People and permissions: people, roles (APP-BASE-5) ──────────────────────────────────────────────────────────────


def people_of(slug: str) -> list[dict[str, Any]]:
    """The people of the business of ``slug``, owner first: those who entered (their ``Membership``, control's) and
    those the SaaS's last photo names that have not entered yet (``members``: erplora.com's accepted ones), each once,
    with what the hub keeps of their way in (``Credential``) and their name in it (``Profile``). Two reads per side,
    never a join: who is a member is control's and the ways in are the hub's."""
    found: dict[str, dict[str, Any]] = {}
    memberships = Membership.objects.filter(host=slug, user__is_active=True).select_related("user")
    for membership in memberships:
        user = membership.user
        found[user.get_username()] = {
            "user": user,
            "role": membership.role,
            "email": user.email,
            "name": user.get_full_name(),
            "entered": True,
        }
    for member in _photo_members(slug):
        username = f"{people_rules.SAAS_PREFIX}{member['user_id']}"
        if username not in found:
            found[username] = {
                "user": None,
                "role": member["role"],
                "email": member.get("email") or "",
                "name": member.get("name") or "",
                "entered": False,
            }
    credentials = {row.username: row for row in Credential.objects.filter(username__in=list(found))}
    profiles = {row.username: row for row in Profile.objects.filter(username__in=list(found))}
    people = []
    for username, person in found.items():
        credential = credentials.get(username)
        profile = profiles.get(username)
        own = f"{profile.first_name} {profile.last_name}".strip() if profile is not None else ""
        name = own or person["name"] or person["email"].split("@", 1)[0] or username
        people.append(
            {
                **person,
                "id": username,
                "name": name,
                "initials": access.initials(name),
                "credential": credential,
                "ways": people_rules.ways(
                    pin=bool(credential and credential.pin_hash), badge=bool(credential and credential.badge_digest)
                ),
            }
        )
    return sorted(people, key=lambda person: (people_rules.role_rank(person["role"]), person["name"].casefold()))


#: The roles the photo's ``members`` may carry: erplora.com's four.
PHOTO_ROLES = frozenset(people_rules.ROLE_ORDER)


def _photo_members(slug: str) -> list[dict[str, Any]]:
    """The ``members`` of the SaaS's last photo of ``slug`` that are well formed; none without a photo."""
    state = Hub.objects.filter(slug=slug).values_list("state", flat=True).first()
    members = state.get("members") if isinstance(state, dict) else None
    if not isinstance(members, list):
        return []
    return [
        member
        for member in members
        if isinstance(member, dict) and str(member.get("user_id") or "") and member.get("role") in PHOTO_ROLES
    ]


def seats_of(slug: str, used: int) -> dict[str, Any]:
    """The places of the plan of the SaaS's last photo (``plan.max_users``; 0 is none) against ``used``."""
    state = Hub.objects.filter(slug=slug).values_list("state", flat=True).first()
    plan = state.get("plan") if isinstance(state, dict) and isinstance(state.get("plan"), dict) else None
    known = plan is not None and _is_count(plan.get("max_users"))
    limit = plan["max_users"] or None if known else None
    return {"known": known, "used": used, "limit": limit, "full": limit is not None and used >= limit}


def person_out(ctx: OperationContext, person: dict[str, Any]) -> dict[str, Any]:
    """A person as Employees shows them to who asks: the address only to who runs the business, and their own."""
    me = signed_in_username(ctx) == person["id"]
    return {
        "id": person["id"],
        "name": person["name"],
        "initials": person["initials"],
        "email": person["email"] if (me or ctx.has(ADMINISTER_HUB)) else "",
        "role": person["role"],
        "ways": person["ways"],
        "entered": person["entered"],
        "me": me,
    }


def is_a_person(actor: Any) -> bool:
    """Whether ``actor`` is a signed-in person (a control user), not the platform, an API key or nobody."""
    return hasattr(actor, "get_username") and bool(getattr(actor, "is_authenticated", False))


def hub_user_of(ctx: OperationContext) -> HubUser | None:
    """The caller's ``HubUser`` in the active hub's database, read only (``base.services.acting_hub_user`` makes it);
    ``None`` for the platform, an API key, nobody, or a person who has none there yet."""
    if not is_a_person(ctx.actor):
        return None
    return HubUser.objects.filter(username=ctx.actor.get_username()).first()


# Not an assistant tool: what the cards of the writes that link a person read to name them (``REFERS``).
@operation("base.hub_user.get", kind="query", permission=VIEW_HOME, input=HubUserGetIn, output=HubUserOut, ai=INTERNAL)
def hub_user_get(ctx: OperationContext, data: HubUserGetIn) -> dict[str, Any]:
    """A person of this business by their id in its database (``base.HubUser``), with access to it (a ``Membership``
    on the scope's host, control's): how a staff record's user or a conversation's assignee is named on the
    assistant's card. Anyone else, here or in another business, is ``NotFound``."""
    person = HubUser.objects.filter(pk=data.id).first()
    if person is None or not Membership.objects.filter(host=ctx.scope.key, user__username=person.username).exists():
        raise NotFound(gettext("That person is not in this business."), code="base.person_not_found")
    return {"id": person.pk, "name": person.display_name}


def signed_in_username(ctx: OperationContext) -> str:
    return ctx.actor.get_username() if hasattr(ctx.actor, "get_username") else ""


def person_of(ctx: OperationContext, person_id: str) -> dict[str, Any]:
    """The person ``person_id`` of this business; ``NotFound`` for anyone else (another business's, nobody)."""
    for person in people_of(ctx.scope.key):
        if person["id"] == person_id:
            return person
    raise NotFound(gettext("That person is not in this business."), code="base.person_not_found")


def signed_in_role(ctx: OperationContext) -> str:
    username = signed_in_username(ctx)
    role = Membership.objects.filter(host=ctx.scope.key, user__username=username).values_list("role", flat=True).first()
    return role or ""


def person_detail_out(ctx: OperationContext, person: dict[str, Any]) -> dict[str, Any]:
    """A person's page (BASE-G10): what the hub keeps of their way in and what who asks may change of it."""
    actor, actor_role = signed_in_username(ctx), signed_in_role(ctx)
    credential = person["credential"]

    def may(badge: bool) -> bool:
        return people_rules.refusal(
            actor=actor, actor_role=actor_role, target=person["id"], target_role=person["role"], badge=badge
        ) is None

    return {
        **person_out(ctx, person),
        "pin_set_at": credential.pin_set_at if credential and credential.pin_hash else None,
        "badge_set_at": credential.badge_set_at if credential and credential.badge_digest else None,
        "may": {"remove_pin": may(False), "set_badge": may(True)},
    }


@operation(
    "base.person.list",
    kind="query",
    permission=VIEW_HOME,
    input=PersonListIn,
    output=PersonListOut,
    ai=AI(
        description=(
            "Lists the people of this business: name, role (owner, admin, manager, employee), how each one gets in "
            "(their erplora.com account, and a PIN or a badge at the shared tills) and whether they entered yet; and "
            "the places of the plan taken. Inviting, changing a role or removing someone is done on erplora.com."
        ),
        asks={
            "en": ("who has access to the business?", "list everyone and their role", "who still hasn't signed in?"),
            "es": ("¿quién tiene acceso al negocio?", "¿quién puede entrar en el negocio y con qué rol?"),
        },
    ),
)
def person_list(ctx: OperationContext, data: PersonListIn) -> dict:
    """Employees › Personal (BASE-G11, G142, G138): every person once, owner first, with the plan's places."""
    found = people_of(ctx.scope.key)
    return {"people": [person_out(ctx, person) for person in found], "seats": seats_of(ctx.scope.key, len(found))}


@operation(
    "base.person.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=PersonIn,
    output=PersonDetailOut,
    ai=AI(
        description=(
            "Reads one person of this business by their id: role, how they get in (PIN, badge), since when, and "
            "whether who asks may take their PIN away or give them a badge."
        ),
        asks={
            "en": ("how does Luis get in, PIN or badge?", "can Ana still use her PIN?"),
            "es": ("¿cómo entra Luis, con PIN o con placa?", "¿Ana tiene placa?"),
        },
    ),
)
def person_detail(ctx: OperationContext, data: PersonIn) -> dict:
    """A person's page (BASE-G10), for who runs the business."""
    return person_detail_out(ctx, person_of(ctx, data.person))


@operation(
    "base.role.list",
    kind="query",
    permission=VIEW_HOME,
    input=RoleListIn,
    output=RoleListOut,
    ai=AI(
        description=(
            "Lists the roles of this business (owner, admin, manager, employee): how many people have each one and how "
            "many permissions of the apps it gives. Roles are given on erplora.com."
        ),
        asks={
            "en": ("how many managers do we have?", "what can a manager do here?"),
            "es": ("¿qué roles hay en el negocio?", "¿cuántos encargados tenemos?"),
        },
    ),
)
def role_list(ctx: OperationContext, data: RoleListIn) -> dict:
    """Employees › Roles (BASE-G143): erplora.com's four, from the top, with their people and permissions."""
    found = people_of(ctx.scope.key)
    configs = all_live_app_configs()
    everything = {permission for config in configs for permission in config.permissions}
    with translation.override(ctx.language):
        return {
            "roles": [
                {
                    "key": role.value,
                    "label": str(role.label),
                    "origin": "basic",
                    "members": sum(1 for person in found if person["role"] == role),
                    "permissions": len(
                        everything if role in FULL_ACCESS_ROLES else permissions_for_role(configs, role.value)
                    ),
                }
                for role in people_rules.ROLE_ORDER
            ]
        }


# ── People and permissions: the business's API keys (APP-BASE-5) ───────────────────────────────────────────────────


def api_key_out(key: ApiKey) -> dict[str, Any]:
    """A key as Employees › API keys shows it: never its token, only its first characters."""
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "mode": key.mode,
        "scopes": key.scopes if key.mode == ApiKey.Mode.PER_APP and isinstance(key.scopes, dict) else {},
        "rate_per_minute": key.rate_per_minute,
        "created_by": key.created_by,
        "created_at": key.created_at,
        "rotated_at": key.rotated_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
    }


def api_apps(ctx: OperationContext) -> list[dict[str, Any]]:
    """The modules this business has on (not blocked by its plan, not turned off) that publish operations
    (``expose_api``), each with whether it publishes queries (a key may read it) and commands (write), by name in who
    asks's language."""
    blocked = entitlement.blocked_apps(ctx.scope) | activation.off_apps(ctx.scope)
    published: dict[str, set[str]] = {}
    for op in operation_registry.values():
        if op.expose_api:
            published.setdefault(op.app_label, set()).add(op.kind)
    with translation.override(ctx.language):
        apps = [
            {"id": config.label, "name": str(config.verbose_name), "read": "query" in kinds, "write": "command" in kinds}
            for config in module_configs()
            if (kinds := published.get(config.label)) and config.label not in blocked
        ]
    return sorted(apps, key=lambda app: app["name"].casefold())


@operation(
    "base.api_key.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApiKeyListIn,
    output=ApiKeyListOut,
    ai=AI(
        description=(
            "Lists this business's API keys for other systems: name, the start of the token (never the whole), what "
            "each may do (all, read, write or per app), its requests a minute, when it was last used and whether it "
            "was revoked; and the apps whose API a key can reach."
        ),
        asks={
            "en": (
                "which API keys do we have?",
                "what systems are connected with a key?",
                "when was the Holded key last used?",
            ),
            "es": (
                "¿qué claves de API tenemos?",
                "¿qué programas están conectados con clave?",
                "¿cuándo se usó por última vez la clave de Holded?",
            ),
        },
    ),
)
def api_key_list(ctx: OperationContext, data: ApiKeyListIn) -> dict:
    """Employees › API keys (BASE-G149, G05): every key, the newest first, and the apps a key per app may reach. While
    the business shares phase 1's database with others, none is available (``base.services.has_own_database``)."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    available = bool(hub is not None and hub.db_name)
    keys = [api_key_out(key) for key in ApiKey.objects.all()] if available else []
    return {"available": available, "keys": keys, "apps": api_apps(ctx)}


@operation(
    "base.api_key.detail",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApiKeyIdIn,
    output=ApiKeyOut,
    ai=AI(
        description=(
            "Reads one API key of this business by its id, as the list of keys shows it: its name, the start of its "
            "token (never the whole), what it may do and whether it was revoked."
        ),
        asks={
            "en": ("what can the accountant's API key do?", "show me the Shopify key"),
            "es": ("¿qué permisos tiene la clave de la gestoría?", "dame los datos de la clave de Shopify"),
        },
    ),
)
def api_key_detail(ctx: OperationContext, data: ApiKeyIdIn) -> dict:
    """One key of Employees › API keys; none while the business shares phase 1's database (``api_key_list``)."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    key = ApiKey.objects.filter(pk=data.id).first() if hub is not None and hub.db_name else None
    if key is None:
        raise NotFound(gettext("That key no longer exists. Refresh the list and try again."))
    return api_key_out(key)


# ── People and permissions: a manager's approval (APP-BASE-5) ──────────────────────────────────────────────────────
from base import approvals as approval_rules  # noqa: E402
from base.models import Approval  # noqa: E402
from base.schemas import ApprovalExportIn, ApprovalExportOut, ApprovalListIn, ApprovalListOut, ApproversIn, ApproversOut  # noqa: E402
from base.permissions import permissions_for  # noqa: E402

#: Employees › Approvals shows the newest 500.
APPROVALS_SHOWN = 500


def holds(user, scope, permission: str) -> bool:
    """Whether ``user`` holds ``permission`` on ``scope``, as ``@operation`` asks it (wildcards included)."""
    return OperationContext(scope=scope, actor=user, permissions=permissions_for(user, scope)).has(permission)


def approval_action(operation: str, figures: dict | None = None, currency: str | None = None) -> str:
    """What an approval approved, in words: the app's own (with the ``figures`` of what it let through, in the active
    language and in ``currency``, when its app says it with them), else «An action of <app>», else that nobody names
    it now."""
    found = approval_rules.approvable(operation)
    if found is not None:
        return approval_rules.label_of(found[0], figures, currency=currency) or found[1]
    config = next((c for c in all_live_app_configs() if c.label == operation.split(".", 1)[0]), None)
    if config is not None:
        return gettext("An action of %(app)s") % {"app": config.verbose_name}
    return gettext("An action no app names now")


@operation(
    "base.approval.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApprovalListIn,
    output=ApprovalListOut,
    ai=AI(
        description=(
            "Lists the actions a manager approved with their PIN or badge, the newest first: when, what in words, who "
            "asked, who approved, how, and whether the approval was used."
        ),
        asks={
            "en": (
                "who approved that discount?",
                "show me today's approvals",
                "what did the manager authorise with their PIN?",
            ),
            "es": (
                "¿quién aprobó la anulación de ayer?",
                "enséñame las aprobaciones de hoy",
                "¿qué ha autorizado el encargado con su PIN?",
            ),
        },
    ),
)
def approval_list(ctx: OperationContext, data: ApprovalListIn) -> dict:
    """Employees › Approvals (BASE-G145): the record of approvals, read only."""
    rows = list(Approval.objects.order_by("-created_at", "-id")[:APPROVALS_SHOWN])
    currency = approval_rules.currency_of(ctx.scope) if any(row.figures for row in rows) else None
    return {
        "approvals": [
            {
                "id": row.id,
                "at": row.created_at,
                "action": approval_action(row.operation, row.figures, currency),
                "operation_label": approval_action(row.operation),
                "operation": row.operation,
                "requested_by": row.requested_by_name,
                "approved_by": row.approved_by_name,
                "way": row.way,
                "used": row.used_at is not None,
                "used_at": row.used_at,
            }
            for row in rows
        ]
    }


def _approvals_kept(data: ApprovalExportIn, currency: str | None):
    """The record with the list's search and filters: the days in the business's time zone, the search on what the list
    shows (the action in words, with its figures, and the two names), in any case."""
    rows = Approval.objects.order_by("-created_at", "-id")
    if data.at_from:
        rows = rows.filter(created_at__date__gte=data.at_from)
    if data.at_to:
        rows = rows.filter(created_at__date__lte=data.at_to)
    if data.operation:
        rows = rows.filter(operation=data.operation)
    if data.way:
        rows = rows.filter(way=data.way)
    if data.used is not None:
        rows = rows.filter(used_at__isnull=not data.used)
    needle = data.search.strip()
    if needle:
        named = [
            name
            for name in rows.order_by().values_list("operation", flat=True).distinct()
            if needle.lower() in approval_action(name).lower()
        ]
        figured = [
            pk
            for pk, name, figures in rows.filter(figures__isnull=False).values_list("id", "operation", "figures")
            if needle.lower() in approval_action(name, figures, currency).lower()
        ]
        rows = rows.filter(
            Q(requested_by_name__icontains=needle)
            | Q(approved_by_name__icontains=needle)
            | Q(operation__in=named)
            | Q(id__in=figured)
        )
    return rows


def _approval_cell(text: str) -> str:
    """A cell a spreadsheet must not run: an apostrophe in front of what it would read as a formula."""
    return f"'{text}" if text.startswith(blueprint.FORMULA_STARTS) else text


@operation(
    "base.approval.export",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ApprovalExportIn,
    output=ApprovalExportOut,
    ai=AI(
        description=(
            "Exports the record of approvals as a CSV file, the newest first, with the search and the filters of "
            "Employees › Approvals (days, action, PIN or badge, used or not): when, what in words, who approved, who "
            "asked, how and whether it was used. It names people of the business."
        ),
        asks={
            "en": ("show me last month's manager approvals", "list the approvals made with a badge this week"),
            "es": ("enséñame las autorizaciones del mes pasado", "¿qué se aprobó con placa esta semana?"),
        },
    ),
)
def approval_export(ctx: OperationContext, data: ApprovalExportIn) -> dict:
    """Employees › Approvals › «Export CSV» (BASE-F85): every approval the list's search and filters keep, not only the
    newest it shows, in words and in the person's language."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(
        [
            pgettext("approvals export", "When"),
            pgettext("approvals export", "Action"),
            pgettext("approvals export", "Approved by"),
            pgettext("approvals export", "Asked by"),
            pgettext("approvals export", "With"),
            pgettext("approvals export", "State"),
        ]
    )
    count = 0
    currency = approval_rules.currency_of(ctx.scope) if Approval.objects.filter(figures__isnull=False).exists() else None
    for row in _approvals_kept(data, currency):
        writer.writerow(
            [
                timezone.localtime(row.created_at).strftime("%Y-%m-%d %H:%M"),
                _approval_cell(approval_action(row.operation, row.figures, currency)),
                _approval_cell(row.approved_by_name),
                _approval_cell(row.requested_by_name),
                str(Approval.Way(row.way).label),
                pgettext("approvals export", "Used") if row.used_at else pgettext("approvals export", "Not used"),
            ]
        )
        count += 1
    return {"filename": "approvals.csv", "content_type": "text/csv", "rows": count, "csv": buffer.getvalue()}


@operation(
    "base.approval.approvers",
    kind="query",
    permission=VIEW_HOME,
    input=ApproversIn,
    output=ApproversOut,
    ai={
        "description": "Not an assistant tool: names who of the business can approve one refused action with their "
        "PIN (they hold its permission and have a PIN), for the approval dialog."
    },
)
def approval_approvers(ctx: OperationContext, data: ApproversIn) -> dict:
    """«Who approves it?» (BASE-G136): the people of the business with a PIN who may do the action themselves, by name;
    nobody for an action no app names."""
    found = approval_rules.approvable(data.operation)
    pin_length = access.pin_length_or_default(access_settings().pin_length)
    if found is None:
        return {"people": [], "pin_length": pin_length}
    op = found[0]
    people = [
        {"id": str(credential.pk), "name": face_name(user), "initials": access.initials(face_name(user))}
        for credential, user in pin_people(ctx.scope.key)
        if holds(user, ctx.scope, op.permission)
    ]
    return {"people": sorted(people, key=lambda person: person["name"].casefold()), "pin_length": pin_length}



# ── People and permissions: the API's documentation (APP-BASE-5) ───────────────────────────────────────────────────
from base import api_docs  # noqa: E402
from base.models import ApiSettings  # noqa: E402
from base.schemas import ApiDocIn, ApiDocOut, ApiDocSettingsIn, ApiDocSettingsOut  # noqa: E402
from live.errors import Conflict  # noqa: E402


def api_docs_enabled() -> bool:
    row = ApiSettings.objects.first()
    return bool(row is not None and row.docs_enabled)


@operation(
    "base.api_doc.settings",
    kind="query",
    permission=VIEW_HOME,
    input=ApiDocSettingsIn,
    output=ApiDocSettingsOut,
    ai=AI(
        description=(
            "Says whether this business shows the documentation of its API, and whether who asks may change it."
        ),
        asks={
            "en": ("is our API documentation visible?", "can the developer see the API docs?"),
            "es": ("¿está publicada la documentación de la API?", "¿el programador puede ver la doc de la API?"),
        },
    ),
)
def api_doc_settings(ctx: OperationContext, data: ApiDocSettingsIn) -> dict:
    """«Show the API documentation» in Settings › General (BASE-G100); off without a row."""
    return {"docs_enabled": api_docs_enabled(), "can_change": ctx.has(ADMINISTER_HUB)}


@operation(
    "base.api_doc.get",
    kind="query",
    permission=VIEW_HOME,
    input=ApiDocIn,
    output=ApiDocOut,
    ai={
        "description": "Not an assistant tool (a long technical document): the OpenAPI document of the API this "
        "business's apps publish for other systems, when the business shows it."
    },
)
def api_doc_get(ctx: OperationContext, data: ApiDocIn) -> dict:
    """The API's documentation (BASE-G150, G48): what the apps this business has publish; not given while hidden."""
    if not api_docs_enabled():
        raise Conflict(gettext("The API documentation is hidden in this business."), code="base.api_docs_hidden")
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    apps = api_apps(ctx)
    return {
        "document": api_docs.public_document({app["id"] for app in apps}),
        "apps": apps,
        "keys_available": bool(hub is not None and hub.db_name),
    }


# ── Files (APP-BASE-8) ─────────────────────────────────────────────────────────────────────────────────────────
# The old hub's Files (``GET /api/media``, ``/raw``; HUB_SHELL-F130, F132): the business's files in the hub file store
# (``base.files``), on the hub of the request only. Everyone of the hub sees and opens them.
VIEW_FILES = "base.view_files"
UPLOAD_FILES = "base.upload_files"
DELETE_FILES = "base.delete_files"


def space_limit(ctx: OperationContext) -> int | None:
    """The space for files of the plan in the SaaS's last photo of the hub of ``ctx``; ``None``: no limit."""
    return files.space_limit(Hub.objects.filter(slug=ctx.scope.key).values_list("state", flat=True).first())


def refuse_past_the_plans_space(ctx: OperationContext, store: Storage, size: int) -> None:
    """Files' 409 ``base.file_no_space`` (``base.files.refuse_past_the_space``) when ``size`` more bytes go past the
    space the plan of ``ctx``'s hub includes, said in the caller's language (an API key's or the assistant's call has
    no request). For the apps that keep a file in the hub file store: it takes the plan's space as Files does."""
    with translation.override(ctx.language):
        files.refuse_past_the_space(store, hub_id(ctx.scope), size, limit_bytes=space_limit(ctx))


@operation(
    "base.file.list",
    kind="query",
    permission=VIEW_FILES,
    input=FileListIn,
    output=FileListOut,
    expose_api=True,
    ai=AI(
        description=(
            "Lists the business's files: every folder, and the files of one folder by its path (the folder "
            "«Facturas/2026»; empty: the top), each with its name, size and date, and the space they take against what "
            "the plan includes."
        ),
        asks={
            "en": ("show me our files", "how much storage are we using?", "what's in the Contracts folder?"),
            "es": ("enséñame los archivos del negocio", "¿cuánto espacio llevamos ocupado?"),
        },
    ),
)
def file_list(ctx: OperationContext, data: FileListIn) -> dict:
    """BASE-G82: the tree, the folder's files, the space used and what this person may do with them."""
    with translation.override(ctx.language):
        listing = files.listing(storages["hub_files"], hub_id(ctx.scope), data.folder)
    used = listing.pop("used_bytes")
    return {
        **listing,
        "space": {"used_bytes": used, "limit_bytes": space_limit(ctx)},
        "can": {"upload": ctx.has(UPLOAD_FILES), "delete": ctx.has(DELETE_FILES)},
    }


@operation(
    "base.file.read",
    kind="query",
    permission=VIEW_FILES,
    input=FileReadIn,
    output=FileOut,
    expose_api=True,
    ai=AI(
        description=(
            "Finds one file of the business by its path (the file «Facturas/marzo.pdf»): its name, size and type. Its "
            "bytes are read at the same address by whoever may see the files."
        ),
        asks={
            "en": ("find the file Invoices/march.pdf", "how big is the contract PDF?"),
            "es": ("búscame el archivo Facturas/marzo.pdf", "¿cuánto pesa ese archivo?"),
        },
    ),
)
def file_read(ctx: OperationContext, data: FileReadIn) -> dict:
    """BASE-G84: the file, described; ``base.api`` streams its bytes to the person who asked."""
    with translation.override(ctx.language):
        return files.describe(storages["hub_files"], hub_id(ctx.scope), data.path)


# ── Assistant (APP-BASE-9) ──────────────────────────────────────────────────────────────────────────────────────

from live.errors import OperationError  # noqa: E402 - the assistant's block keeps its imports with it

from pydantic import ValidationError  # noqa: E402

from base import assistant  # noqa: E402
from base.schemas import AssistantUsageIn, AssistantUsageOut, DocsSearchIn, DocsSearchOut  # noqa: E402


@operation(
    "base.assistant.usage",
    kind="query",
    permission=VIEW_HOME,
    input=AssistantUsageIn,
    output=AssistantUsageOut,
    ai={"description": "Not an assistant tool (the panel's own footer: the messages of the month left)."},
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def assistant_usage(ctx: OperationContext, data: AssistantUsageIn) -> dict:
    """This month's messages of the assistant as erplora.com counts them (BASE-G122): used, of how many, and when
    they come back. What cannot be read is an error, never a number made up."""
    try:
        usage = assistant.usage(ctx.scope)
    except assistant.GatewayError:
        raise OperationError(
            gettext("The assistant's plan could not be read now."), code="base.assistant_unavailable", status=503
        ) from None
    return {
        "used": int(usage.get("used") or 0),
        "limit": int(usage.get("limit") or 0),
        "resets_at": usage.get("resets_at"),
        "demo": bool(usage.get("demo")),
    }


@operation(
    "base.docs.search",
    kind="query",
    permission=VIEW_HOME,
    input=DocsSearchIn,
    output=DocsSearchOut,
    ai=AI(
        description=(
            "Searches ERPlora's help and the documentation of its apps for how-to questions (how to do something, what "
            "a screen or option means, plans and prices): returns up to 8 cited excerpts. Not for the business's own "
            "records."
        ),
        asks={
            "en": (
                "how do I close the till at night?",
                "what does a shared device mean?",
                "how much is the Standard plan?",
            ),
            "es": (
                "¿cómo se hace una devolución?",
                "¿qué significa dispositivo compartido?",
                "¿cuánto cuesta el plan Standard?",
            ),
        },
    ),
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile (in a turn, its route asked first).
    database=False,
)
def docs_search(ctx: OperationContext, data: DocsSearchIn) -> DocsSearchOut:
    """The excerpts of ERPlora's documentation nearest to the person's question, in their language (saas
    ASSISTANT-F28): erplora.com's one index, never one of the Hub's. What it cannot answer is an error the assistant
    relays, never excerpts made up."""
    try:
        return DocsSearchOut.model_validate(assistant.searched_docs(ctx, query=data.query, limit=data.limit))
    except (assistant.GatewayError, ValidationError):
        with translation.override(ctx.language):
            message = gettext("ERPlora's documentation could not be searched now.")
        raise OperationError(message, code="base.assistant_unavailable", status=503) from None


# ── Locations (round 2026-10-24b, multi-location) ──────────────────────────────────────────────────────────────────

from base.models import Location  # noqa: E402
from base.schemas import LocationListIn, LocationListOut  # noqa: E402


@operation(
    "base.location.list",
    kind="query",
    permission=VIEW_HOME,
    input=LocationListIn,
    output=LocationListOut,
    ai=AI(
        description=(
            "Lists the places this business works in (its shops, bars or salons), the default one first, and whether "
            "each is still in use. A business with one place has only its default one."
        ),
        asks={
            "en": ("which shops do we have?", "list our locations", "which is our main salon?"),
            "es": ("¿qué locales tenemos?", "¿cuáles son nuestras tiendas?", "¿cuál es el local principal?"),
        },
    ),
)
def location_list(ctx: OperationContext, data: LocationListIn) -> dict:
    """The business's locations, for everyone of the hub: the default first, then by name, those no longer in use
    too."""
    rows = Location.objects.order_by("-is_default", "name", "id")
    return {
        "locations": [
            {"id": row.id, "name": row.display_name, "is_default": row.is_default, "is_active": row.is_active}
            for row in rows
        ]
    }


# ── The shared image library (round 2026-10-30, base.image_catalog) ────────────────────────────────────────────────

from base import image_catalog  # noqa: E402
from base.schemas import CatalogImageOut, CatalogImagePage, CatalogImageRefIn, CatalogImageSearchIn  # noqa: E402

LIBRARY_UNAVAILABLE = gettext_lazy("The image library could not be loaded.")


def image_library(ctx: OperationContext) -> image_catalog.Library:
    """The shared image library, or the 503 ``base.image_library_unavailable`` in ``ctx``'s language when its manifest
    cannot be read: an empty answer would say «no image» when the truth is «not now». Inventory, Services and Combos
    ask it too, so the person reads the same sentence from every screen."""
    try:
        return image_catalog.library()
    except image_catalog.LibraryUnavailable:
        with translation.override(ctx.language):
            raise OperationError(
                str(LIBRARY_UNAVAILABLE), code="base.image_library_unavailable", status=503
            ) from None


def business_language(ctx: OperationContext) -> str:
    """The language the business works in, as erplora.com registered it (Settings › Business), else the deployment's:
    what its products and services are named in, so what the library's images are titled in on its screens."""
    language = Hub.objects.filter(slug=ctx.scope.key).values_list("language", flat=True).first()
    return language or settings.LANGUAGE_CODE


@operation(
    "base.catalog_image.search",
    kind="query",
    permission=VIEW_HOME,
    input=CatalogImageSearchIn,
    output=CatalogImagePage,
    ai=AI(
        description=(
            "Finds an image for a product, a service or a set menu in ERPlora's shared image library by what it is "
            "called, in Spanish or English («café con leche», «women's haircut»), the best match first, each with its "
            "title and the reference (catalog:<folder>/<name>) that sets it as the image of a product, a service or a "
            "set menu. Empty: the whole library by title."
        ),
        asks={
            "en": (
                "find a picture of a cappuccino",
                "is there an image for a women's haircut?",
                "look for a burger photo in the library",
            ),
            "es": (
                "búscame una foto de café con leche",
                "¿hay alguna imagen de corte de pelo de mujer?",
                "encuéntrame un dibujo de hamburguesa",
            ),
        },
    ),
)
def catalog_image_search(ctx: OperationContext, data: CatalogImageSearchIn) -> dict:
    """The library is everyone's: who may see the hub's Home may look an image up (the screens that set one need their
    own app's permission). Any language matches; titled in the business's (INVENTORY-F30: in English when it is not
    Spanish)."""
    language = business_language(ctx)
    found = image_library(ctx).search(data.query, language, folder=data.folder)
    return {
        "rows": [image.row(language) for image in found[data.offset : data.offset + data.limit]],
        "total": len(found),
        "limit": data.limit,
        "offset": data.offset,
    }


@operation(
    "base.catalog_image.get",
    kind="query",
    permission=VIEW_HOME,
    database=False,
    input=CatalogImageRefIn,
    output=CatalogImageOut,
    ai=AI(
        description=(
            "Says which image of the shared library a reference (catalog:<folder>/<name>) names: its title in the "
            "person's language and where it is served."
        ),
        asks={
            "en": ("which picture is catalog:drinks/espresso?", "what's that library image called?"),
            "es": ("¿qué foto es catalog:bebidas/espresso?", "¿cómo se llama esa imagen de la biblioteca?"),
        },
    ),
)
def catalog_image_get(ctx: OperationContext, data: CatalogImageRefIn) -> dict:
    """What the assistant's card says of an image a write sets (``refers``): its title in the person's language (the
    card's), never the raw reference."""
    from base.images import IMAGE_UNKNOWN

    parsed = image_catalog.parse_reference(data.reference)
    image = image_library(ctx).get(*parsed) if parsed else None
    if image is None:
        with translation.override(ctx.language):
            raise NotFound(str(IMAGE_UNKNOWN), code="base.image_unknown")
    return image.row(ctx.language)
