"""Read operations of base: the session's ``me``, the registry's row of a hub (``base.hub.get``), a demo's status
(``base.demo.get``) and the Home's three live queries (``base.setup.status``, ``base.widget.list``,
``base.bell.counters``; their rules are ``base.home``'s); and Settings › Data's reads (APP-BASE-2): the catalogue of
templates, what a blueprint brings, the export, the loads and the apps' data (their rules are ``base.blueprint``'s)."""

import base64
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.db.models import Max
from django.http import HttpRequest
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy, ngettext
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound, Unauthorized
from live.meta import Category, all_live_app_configs, permissions_for_role
from live.models import OutboxEvent
from live.operations import operation

from base import access, blueprint, business, entitlement, home, system
from base.auth import saas_url
from base.models import (
    AccessSettings,
    Credential,
    EventDelivery,
    Hub,
    ImportBatch,
    Membership,
    Profile,
    SessionOwner,
    TrustedDevice,
)
from base.operations import hub_id
from base.permissions import ADMINISTER_HUB, FULL_ACCESS_ROLES, VIEW_HOME
from base.registry import hub_answer, internal_only
from base.relay import active_apps
from base.storage import media_url
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
    DeviceListIn,
    DeviceListOut,
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
    ImportListIn,
    ImportListOut,
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
from base import people as people_rules
from base.schemas import ApiKeyListIn, ApiKeyListOut, PersonDetailOut, PersonIn, PersonListIn, PersonListOut, RoleListIn, RoleListOut
from base.models import ApiKey
from live.meta import module_configs
from live.operations import registry as operation_registry


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
    # Named as in this hub: its «My profile» name, else its account's (APP-BASE-3).
    return {"id": str(actor.pk), "label": person_label(actor)}


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
    the SaaS counts) and the devices in use (those with a session open on this hub: the ones the cap of BASE-G57
    keeps, APP-BASE-3). Memory, CPU and database size are gone with the old process per hub (PLAN-HUB §1a):
    erplora.com measures the use. For who runs the business."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    state = hub.state if hub is not None and isinstance(hub.state, dict) else {}
    plan = state.get("plan") if isinstance(state.get("plan"), dict) else None
    known = plan is not None and all(_is_count(plan.get(field)) for field in ("max_users", "max_devices"))
    people = Membership.objects.filter(host=ctx.scope.key, user__is_active=True).count()
    devices = (
        SessionOwner.objects.filter(host=ctx.scope.key, session__expire_date__gt=timezone.now())
        .exclude(device_id=None)
        .values("device_id")
        .distinct()
        .count()
    )
    return {
        "known": known,
        "people": {"used": people, "limit": _limit(plan, "max_users") if known else None},
        "devices": {"used": devices, "limit": _limit(plan, "max_devices") if known else None},
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
    ai={
        "description": "Lists the templates of businesses this hub can load (a restaurant, a hair salon…): what each "
        "one brings (its apps, its menu or services, its tables) and whether this business is still empty."
    },
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
    ai={
        "description": "Writes a .blueprint.zip of this business: the apps chosen and, of those marked, their data. A "
        "template never takes personal data (customers); a backup takes them. People, PINs and fiscal data never.",
        "risk": "high",
    },
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
        return {
            "filename": blueprint.file_name(data.name, data.language),
            "content_type": "application/zip",
            "content_base64": base64.b64encode(blueprint.write_zip(bundle)).decode("ascii"),
        }


@operation(
    "base.import.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=ImportListIn,
    output=ImportListOut,
    ai={
        "description": "Lists the templates and files loaded into this business, newest first, each with its report, "
        "whether it can be undone and whether what did not go in can be loaded again."
    },
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
    "base.dataset.list",
    kind="query",
    permission=ADMINISTER_HUB,
    input=DatasetListIn,
    output=DatasetListOut,
    ai={"description": "Lists the apps on in this business and, of each, what can travel in an export and how many rows it has."},
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
    ai={
        "description": "Reads this business's name, country, time zone, language and currency, as erplora.com "
        "registered it. They are changed on erplora.com by the owner or an administrator, never here; the country no "
        "longer changes once the business is ready, and the currency is always the country's."
    },
)
def business_get(ctx: OperationContext, data: BusinessIn) -> dict:
    """Settings › Business (BASE-G97…G99) and what the old ``/api/hub/context`` gave (BASE-G43): the business as the
    SaaS registered it, from the registry of this scope, never another's. The currency is its country's
    (``base.business``); a demo has no business on erplora.com, hence no address to change it, and the deployment's
    zone and language until the SaaS says otherwise."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    if hub is None:
        raise NotFound(gettext("There is no business here."))
    language = hub.language or settings.LANGUAGE_CODE
    currency = business.currency_of(hub.country)
    return {
        "name": hub.name,
        "country": hub.country,
        "country_name": business.country_name(hub.country, ctx.language),
        "timezone": hub.timezone or settings.TIME_ZONE,
        "language": language,
        "language_name": business.language_name(language, ctx.language),
        "currency": currency,
        "currency_label": business.currency_label(currency, ctx.language),
        "currency_decimals": business.currency_decimals(currency),
        "demo": hub.is_demo,
        "settings_url": "" if hub.is_demo else saas_url(f"/businesses/{hub.id}/settings"),
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
        "plan_url": saas_url("/store/plans"),
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
    ai={"description": "Says whether the device the person is using is shared (a till: PIN, a shift) or personal."},
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
    ai={
        "description": "Lists the devices someone entered this hub from: name, browser, shared or personal, whether "
        "it has a session open now and until when, who entered last and when, and which ones nobody used in 30 days."
    },
)
def device_list(ctx: OperationContext, data: DeviceListIn) -> dict[str, Any]:
    """«Devices» of Settings › General (BASE-G63): never a device's token, which is its proof. Phase 1 lists the rows
    of the shared table (every scope's), as every hub model does until each hub has its database."""
    now = timezone.now()
    here = device_of(ctx.request)
    devices = list(TrustedDevice.objects.order_by("-last_entry_at"))
    until = dict(
        SessionOwner.objects.filter(host=ctx.scope.key, device_id__in=[d.pk for d in devices], session__expire_date__gt=now)
        .values("device_id")
        .annotate(until=Max("session__expire_date"))
        .values_list("device_id", "until")
    )
    rows = [
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
    return {"devices": rows, "unused": sum(row["unused"] for row in rows)}


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
    ai={
        "description": "Reads how the business asks who is at the till: whether the PIN pad shows, when it asks "
        "again (after some minutes without use, or once per shift) and how many digits a PIN has."
    },
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
    ai={"description": "Reads the person's own profile in this hub: name, contact email, language and appearance."},
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
    ai={
        "description": "Lists the people of this business: name, role (owner, admin, manager, employee), how each one "
        "gets in (their erplora.com account, and a PIN or a badge at the shared tills) and whether they entered yet; "
        "and the places of the plan taken. Inviting, changing a role or removing someone is done on erplora.com."
    },
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
    ai={
        "description": "Reads one person of this business by their id: role, how they get in (PIN, badge), since when, "
        "and whether who asks may take their PIN away or give them a badge."
    },
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
    ai={
        "description": "Lists the roles of this business (owner, admin, manager, employee): how many people have each "
        "one and how many permissions of the apps it gives. Roles are given on erplora.com."
    },
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
    """The modules this business has (not blocked by its plan) that publish operations (``expose_api``), each with
    whether it publishes queries (a key may read it) and commands (write), by name in who asks's language."""
    blocked = entitlement.blocked_apps(ctx.scope)
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
    ai={
        "description": "Lists this business's API keys for other systems: name, the start of the token (never the "
        "whole), what each may do (all, read, write or per app), its requests a minute, when it was last used and "
        "whether it was revoked; and the apps whose API a key can reach."
    },
)
def api_key_list(ctx: OperationContext, data: ApiKeyListIn) -> dict:
    """Employees › API keys (BASE-G149, G05): every key, the newest first, and the apps a key per app may reach. While
    the business shares phase 1's database with others, none is available (``base.services.has_own_database``)."""
    hub = Hub.objects.filter(slug=ctx.scope.key).first()
    available = bool(hub is not None and hub.db_name)
    keys = [api_key_out(key) for key in ApiKey.objects.all()] if available else []
    return {"available": available, "keys": keys, "apps": api_apps(ctx)}


# ── People and permissions: a manager's approval (APP-BASE-5) ──────────────────────────────────────────────────────
from base import approvals as approval_rules  # noqa: E402
from base.models import Approval  # noqa: E402
from base.schemas import ApprovalListIn, ApprovalListOut, ApproversIn, ApproversOut  # noqa: E402
from base.permissions import permissions_for  # noqa: E402

#: Employees › Approvals shows the newest 500.
APPROVALS_SHOWN = 500


def holds(user, scope, permission: str) -> bool:
    """Whether ``user`` holds ``permission`` on ``scope``, as ``@operation`` asks it (wildcards included)."""
    return OperationContext(scope=scope, actor=user, permissions=permissions_for(user, scope)).has(permission)


def approval_action(operation: str) -> str:
    """What an approval approved, in words: the app's own, else «An action of <app>», else that nobody names it now."""
    found = approval_rules.approvable(operation)
    if found is not None:
        return found[1]
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
    ai={
        "description": "Lists the actions a manager approved with their PIN or badge, the newest first: when, what "
        "in words, who asked, who approved, how, and whether the approval was used."
    },
)
def approval_list(ctx: OperationContext, data: ApprovalListIn) -> dict:
    """Employees › Approvals (BASE-G145): the record of approvals, read only."""
    rows = Approval.objects.order_by("-created_at", "-id")[:APPROVALS_SHOWN]
    return {
        "approvals": [
            {
                "id": row.id,
                "at": row.created_at,
                "action": approval_action(row.operation),
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
    if found is None:
        return {"people": []}
    op = found[0]
    people = [
        {"id": str(credential.pk), "name": face_name(user), "initials": access.initials(face_name(user))}
        for credential, user in pin_people(ctx.scope.key)
        if holds(user, ctx.scope, op.permission)
    ]
    return {"people": sorted(people, key=lambda person: person["name"].casefold())}
