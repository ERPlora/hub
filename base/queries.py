"""Read operations of base: the session's ``me``, the registry's row of a hub (``base.hub.get``), a demo's status
(``base.demo.get``) and the Home's three live queries (``base.setup.status``, ``base.widget.list``,
``base.bell.counters``; their rules are ``base.home``'s); and Settings › Data's reads (APP-BASE-2): the catalogue of
templates, what a blueprint brings, the export, the loads and the apps' data (their rules are ``base.blueprint``'s)."""

import base64
from typing import Any

from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import operation

from base import blueprint, home
from base.models import EventDelivery, Hub, ImportBatch, Membership
from base.registry import hub_answer, internal_only
from base.relay import active_apps
from base.schemas import (
    BellCountersIn,
    BellCountersOut,
    BlueprintExportIn,
    BlueprintFileOut,
    BlueprintListIn,
    BlueprintListOut,
    DatasetListIn,
    DatasetListOut,
    ImportListIn,
    ImportListOut,
    DemoSlugIn,
    DemoStatusOut,
    HubGetIn,
    HubOut,
    HubsBySlugIn,
    HubsBySlugOut,
    NoticeListIn,
    NoticeListOut,
    SessionMeIn,
    SessionMeOut,
    SetupStatusIn,
    SetupStatusOut,
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
    or a demo's hub): a platform app such as ``base`` is always on and never shows. ``demo`` says when the demo
    ends, on a demo's hub only. No permission: an anonymous visitor gets ``user: None`` and nothing else, which
    tells the SPA to send it to the login.
    """
    # Labels are lazy translations; a live re-run happens outside the request that activated the
    # language, so it is set here.
    demo = _demo_hub(ctx)
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
                if config.navigation
            ],
            "apps": [{"label": config.label, "state": "on"} for config in visible],
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
