"""Schemas of base's operations. ``SessionMeOut`` mirrors ``SessionMe`` of packages/ui (shell/session.ts).

The registry's (``Hub…``) are the bodies of the SaaS's ``/internal/hubs/{id}`` calls (plan 2026-10-17, §1.5):
``HubRegistryIn`` is ``hubs.queries.hub_registry`` of the SaaS, ``HubOut`` what the Hub answers to it. The demos'
(``Demo…``) are those of ``POST /internal/demos`` and ``POST /internal/demos/{slug}/codes``, as the SaaS's
``hubs.hub_client.create_demo`` and ``create_demo_code`` send and read them.
"""

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field, field_validator


def names(read: str, by: str = "id", name: tuple[str, ...] = ("name",)) -> dict:
    """The mark of a datum that names a record by its id (base/assistant.py ``REFERS``): the assistant's card names it
    as ``read`` answers it (the first of ``name`` not empty), never by the id."""
    return {"refers": {"read": read, "by": by, "name": list(name)}}


def in_currency_of(read: str, by: str = "id", code: str = "currency") -> dict:
    """The mark of a datum that names a record in a currency of its own, a cart or a price list (base/assistant.py
    ``CURRENCY``): the assistant's card says the amounts beside it in the currency ``read`` answers (its ``code``)."""
    return {"currency": {"read": read, "by": by, "code": code}}


#: A device by its name or, with none, by what it is («Chrome · macOS»), as Settings › Devices says it.
DEVICE_NAMES = ("name", "agent")


class SessionMeIn(Schema):
    pass


class SessionUser(Schema):
    id: str
    label: str


class SessionScope(Schema):
    kind: str
    key: str


class MenuItem(Schema):
    path: str
    label: str
    icon: str


class MenuGroup(Schema):
    id: str
    label: str
    items: list[MenuItem]


class AppState(Schema):
    label: str
    # "off": no right to it (base.entitlement), turned off by the business, or its tables could not be made
    # (base.activation); "activating" while the hub's own database gets its tables (S3).
    state: Literal["on", "activating", "off"]


class SessionDemo(Schema):
    """The demo the session is in: when it ends (the shell's banner, plan 2026-10-17 §1.6)."""

    expires_at: dt.datetime


class SessionMeOut(Schema):
    user: SessionUser | None
    scope: SessionScope
    permissions: list[str]
    menu: list[MenuGroup]
    apps: list[AppState]
    language: str
    #: Always there; ``None`` on a business's hub.
    demo: SessionDemo | None


class HubRegistryIn(Schema):
    """``PUT /internal/hubs/{id}``: what the SaaS registers a business with."""

    id: UUID
    slug: str
    name: str = Field("", max_length=120)
    country: str = Field("", max_length=2)
    timezone: str = Field("", max_length=64)
    language: str = Field("", max_length=8)
    vertical: str | None = Field(None, max_length=63)


class HubOut(Schema):
    """A hub of the registry, as ``/internal/hubs/{id}`` answers it; ``status`` ``ready`` is what the SaaS waits for."""

    id: UUID
    slug: str
    status: str
    is_demo: bool
    expires_at: dt.datetime | None
    ready_at: dt.datetime | None
    state_version: int


class HubRegisterOut(HubOut):
    #: Whether this call created the row (``202``) or updated it (``200``); not sent to the SaaS.
    created: bool


class MemberIn(Schema):
    """One person of the business as the photo lists them (``hubs.queries`` of the SaaS: its accepted members)."""

    user_id: UUID
    role: Literal["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
    email: str | None = None
    name: str | None = None


class HubStateIn(Schema):
    """``PUT /internal/hubs/{id}/state``: the SaaS's photo (``photo``, as it came) and the parts the Hub applies."""

    id: UUID
    version: int = Field(ge=0)
    status: Literal["active", "past_due", "suspended"] | None = None
    verifactu: dict[str, Any] | None = None
    whatsapp: dict[str, Any] | None = None
    members: list[MemberIn] | None = None
    photo: dict[str, Any]


class HubStateOut(Schema):
    applied: bool
    version: int


class HubUserGetIn(Schema):
    id: UUID = Field(description="The person's id in the business's database.")


class HubUserOut(Schema):
    id: UUID
    name: str = Field(description="Their name, else their email, else how the Hub knows them.")


class HubUserSyncIn(Schema):
    """The people of the SaaS's photo (``members``), for the business's own database (``base.hub_user.sync``), and
    the SaaS accounts the photo just took out of the business (``left``)."""

    members: list[MemberIn]
    left: list[str] = Field(default_factory=list)


class HubUserSyncOut(Schema):
    made: int = Field(description="People of the photo the business's database did not have yet.")
    updated: int = Field(description="People whose name, email or state changed.")
    left: int = Field(description="People no longer in the business, kept with their name, no longer active.")


class SessionRevokeIn(Schema):
    """``POST /internal/sessions/revoke``: the SaaS account whose sessions end, on one business (``hub_id``) or on
    every host, the Hub admin's included (without it)."""

    user_id: UUID
    hub_id: UUID | None = None


class SessionRevokeOut(Schema):
    ended: int


class HubGetIn(Schema):
    id: UUID


class HubCancelIn(Schema):
    id: UUID


class HubRestoreIn(Schema):
    id: UUID


class HubCutFinishIn(Schema):
    """The last step of the cut of a business of phase 1 (``base.tenancy.cut``): its database made, its rows copied
    (``copied``: rows per table, none when it was made again) and seeded with the SaaS's photo of ``seeded_version``."""

    id: UUID
    mode: Literal["recreate", "copy_all"]
    database: str
    schema_apps: dict[str, str]
    copied: dict[str, int]
    dump: str = ""
    seeded_version: int | None = None


class HubCutFinishOut(Schema):
    """``done``: the business now works on its own database; false when a newer photo came while it was seeded (the
    cut applies it and asks again)."""

    done: bool


class HubSeedLocalIn(Schema):
    """``manage.py seed_local_hubs``: the local hubs to leave ready (``a`` and ``b``), each with a database of its own
    (``requested``, the command makes it)."""

    slugs: list[str]


class SeededHub(Schema):
    slug: str
    outcome: Literal["created", "ready_again", "already_ready", "requested"]


class HubSeedLocalOut(Schema):
    hubs: list[SeededHub]


class HubsBySlugIn(Schema):
    slugs: list[str]


class HubStatusOut(Schema):
    slug: str
    #: The registry's status, or ``None`` when no row has this slug.
    status: str | None


class HubsBySlugOut(Schema):
    hubs: list[HubStatusOut]


#: A browser of the SaaS, as the SaaS names it to the Hub: the sha256 (hex) of a random token of its session.
SESSION_KEY_PATTERN = r"^[0-9a-f]{64}$"


class DemoCreateIn(Schema):
    """``POST /internal/demos``: a demo for this browser; ``vertical`` is only noted (no seed in phase 1)."""

    session_key: str = Field(pattern=SESSION_KEY_PATTERN)
    vertical: str | None = Field(None, max_length=63)
    language: str = Field("", max_length=8)


class DemoOut(Schema):
    """The browser's demo; ``created`` says whether this call made it (202, ``requested``) or it was the live one
    (200); ``status`` is the registry's (``ready`` once its database is made)."""

    id: UUID
    slug: str
    status: str
    expires_at: dt.datetime
    created: bool


class DemoCodeIn(Schema):
    """``POST /internal/demos/{slug}/codes``: a one-time code into ``slug`` for the browser that owns it."""

    slug: str = Field(max_length=63)
    session_key: str = Field(pattern=SESSION_KEY_PATTERN)
    language: str = Field("", max_length=8)


class DemoCodeOut(Schema):
    code: str
    expires_at: dt.datetime


class DemoSlugIn(Schema):
    slug: str = Field(max_length=63)


class DemoStatusOut(Schema):
    """A demo of the registry: ``ready`` while it lasts, ``expired`` once ended, ``purged`` once the reaper came."""

    slug: str
    status: str
    expires_at: dt.datetime | None


# --- The Home (PLAN-HUB round 2026-10-21): base.setup.status, base.widget.list, base.bell.counters ---------------


class SetupStatusIn(Schema):
    """No input: the list of this hub, as the person of the request may be told about it."""


class SetupItemOut(Schema):
    key: str = Field(description="«<app>.<step>»: «base.apps», «base.team» or a module's own step.")
    app: str = Field(description="The app that declares the step («base» for the platform's).")
    state: Literal["done", "pending", "unavailable"] = Field(
        description="«unavailable»: ours, not the person's task (nothing could be turned on)."
    )
    level: Literal["legal", "functional", "recommended"] = Field(
        description="«legal» (needed to invoice) is base's list; else the module's «required»."
    )
    required: bool
    actionable: bool = Field(description="False: a pending ⛔ that the person cannot set up (an administrator must).")
    title: str
    description: str
    icon: str
    route: str = Field(description="The screen that completes it.")
    order: int


class SetupStatusOut(Schema):
    total: int
    pending: int
    unavailable: int
    blocking_pending: int = Field(description="Pending ⛔ steps: the invoice is refused until they are done.")
    items: list[SetupItemOut]


class WidgetListIn(Schema):
    """No input: the panels this person may put on the dashboard of this hub."""


class WidgetOut(Schema):
    key: str = Field(description="«<app>.<panel>».")
    app: str
    title: str
    icon: str
    category: str = Field(description="The group of the picker: the panel's own, or its app's name.")
    size: Literal["sm", "md", "lg"]
    default: bool = Field(description="On by default, before the person chooses.")
    kind: str | None = Field(description="How it renders without a component of its own (kpi, stat, sparkline…).")
    operation: str | None = Field(description="The query that feeds it, followed live by the SPA.")
    params: dict[str, Any]
    map: dict[str, str] = Field(description="Prop of the panel → field of the operation's result.")
    options: dict[str, Any] = Field(description="Literal props of the panel.")
    component: str | None = Field(description="A Vue component of the app's frontend/components/, without «.vue».")
    refresh_on: list[str]
    live: bool = Field(description="Its operation is a live query: the SPA follows it, else it asks once.")


class WidgetListOut(Schema):
    widgets: list[WidgetOut]


class BellCountersIn(Schema):
    """No input: the counters above zero this person may see in this hub."""


class BellCounterOut(Schema):
    key: str = Field(description="«<app>.<counter>», or «base.failed_events».")
    app: str
    count: int
    route: str
    label: str
    icon: str


class BellCountersOut(Schema):
    counters: list[BellCounterOut]
    refresh_every: int | None = Field(
        default=None,
        description="Seconds after which the bell reads its counters again, for one whose figure moves as time passes; "
        "none: only when something changes.",
    )


class NoticeListIn(Schema):
    """No input: what the modules on tell this person's device, of the rows their queries give them."""


class DeviceNoticeOut(Schema):
    key: str = Field(description="«<app>.<notice>».")
    app: str
    id: str = Field(description="The id of what happened, as the module's row says it.")
    at: str = Field(description="The instant it happened, as the module's row says it: with key and id, told once.")
    title: str
    body: str = Field(description="Empty when none of its parts is filled in.")
    route: str = Field(description="The screen a tap opens; empty when a field of it is empty.")


class NoticeListOut(Schema):
    notices: list[DeviceNoticeOut] = Field(description="The newest first.")
    sources: list[str] = Field(
        description="«<app>.<notice>» of every notice this person hears, told or not: with none, nothing to ask for."
    )


# ── Apps (APP-BASE-4) ──────────────────────────────────────────────────────────────────────────────────────────


class AppListIn(Schema):
    """No input: the business's apps, all of them (the modules of the deployment, a short fixed list)."""


class AppOut(Schema):
    """A module as the Apps screen paints it: from its ``LiveAppConfig``, with its right (``base.entitlement``)."""

    id: str
    name: str
    icon: str
    category: str
    category_label: str
    summary: str
    #: Bought on erplora.com (``premium``): no price here, the Store has it (PLAN §20.4.3).
    premium: bool
    #: Where its right comes from: ``free``, ``plan``, ``purchase``, ``required`` (with an app that needs it) or
    #: ``missing``.
    right: Literal["free", "plan", "purchase", "required", "missing"]
    #: ``on``, ``off`` (the business turned it off, or never on), ``blocked`` while the business has no right to it;
    #: in a hub with its own database, ``creating`` while its tables are made and ``failed`` when making them failed
    #: (tried again later, or by hand: ``base.app.retry``).
    state: Literal["on", "off", "blocked", "creating", "failed"]
    #: The business turned it on itself (what the plan's limit counts, also while it is being set up); what came along
    #: with another app is not.
    chosen: bool
    #: The first screen of its menu this person may open; ``None``: «Open» is not offered.
    path: str | None
    #: What it needs, transitively (it comes along with it), and the apps on that need it (they go off first).
    requires: list[str]
    required_by: list[str]


class AppListOut(Schema):
    apps: list[AppOut]
    #: erplora.com's Store of this business's modules, where a paid one is bought (never inside the Hub).
    store_url: str
    #: erplora.com's plans of this business, where a higher limit is bought.
    plan_url: str
    #: How many apps the plan lets the business choose (``plan.max_apps`` of the SaaS's photo); ``None``: no limit.
    max_apps: int | None
    #: How many it chose and are on: what the limit counts (what came along with them does not).
    enabled: int


class AppChangeIn(Schema):
    """``base.app.enable`` and ``base.app.disable``: one app of the business, by its id."""

    app: str = Field(max_length=100, description="The app's id, as base.app.list gives it (e.g. «task»).")


class AppNameOut(Schema):
    id: str
    name: str


class AppChangeOut(Schema):
    """The app as it is now, and the apps that went on (or off) with it. ``creating``: its tables are being made in the
    hub's own database (202); the Apps screen follows it until it is on (``base.app.list``)."""

    app: str
    state: Literal["on", "off", "creating"]
    chosen: bool
    #: Turned on with it because it needs them, or off with it because nothing else needs them any more; by name.
    along: list[AppNameOut]


class AppActivationSettleIn(Schema):
    """The worker's step after making a hub's tables (``base.worker``): the apps it took and how it went."""

    apps: list[str] = Field(description="The apps whose tables it made, or tried to.")
    #: ``created``: ``ensure_schema`` ended; ``failed``: it raised (``error``, why); ``locked``: another run held the
    #: hub's schema; ``newer_code``: the request is of a newer code than the worker's.
    outcome: Literal["created", "failed", "locked", "newer_code"]
    error: str = ""


class AppActivationSettleOut(Schema):
    on: list[str]
    failed: list[str]
    waiting: list[str]


class PlanUsageIn(Schema):
    """No input: the plan of the business of the request."""


class LimitOut(Schema):
    #: How much is in use; ``None`` when the Hub does not count it (never a made-up figure).
    used: int | None
    #: The plan's limit; ``None`` when it has none (0 in the SaaS's plan) or the plan is not known.
    limit: int | None


class DatabaseUsageOut(Schema):
    """The size of the business's own database, as the last night measured it (``base.usage``)."""

    available: bool = Field(
        description="False while the business shares its database with others: it has no size of its own yet."
    )
    bytes: int | None = Field(description="Its size in bytes; None before the first night measured it.")
    day: dt.date | None = Field(description="The day (UTC) it was measured; None before the first night.")


class FilesUsageOut(Schema):
    """What the business's files and those of its apps take up, as the last night measured it, against its plan."""

    bytes: int | None = Field(description="What they take up, in bytes; None before the first night measured it.")
    day: dt.date | None = Field(description="The day (UTC) it was measured; None before the first night.")
    limit: int | None = Field(description="The space the plan includes, in bytes; None: no limit, or the plan is not known.")
    percent: int | None = Field(description="How much of that space they take up; None without a limit or a figure.")
    status: Literal["within", "near", "full"] | None = Field(
        description="Within the limit, close to it (from 80 %) or reached; None without a limit or a figure."
    )


class ConnectionsUsageOut(Schema):
    """What the business does at once in its database against what it really has."""

    peak_today: int | None = Field(description="The most transactions at once today; None: not measured today yet.")
    limit: int | None = Field(
        description="What it really has at once: what its plan includes or, if less, what the service gives. None: the plan is not known."
    )
    busy_last_7_days: int | None = Field(
        description="The requests that found no room in the last 7 days; None: never counted yet."
    )
    busy_since: dt.date | None = Field(
        description="Since when they are counted, when that is less than the 7 days; otherwise None."
    )
    status: Literal["within", "near"] | None = Field(
        description="Close to the limit when a request found no room in those 7 days; None: the plan is not known."
    )
    bigger_plan_gives_more: bool = Field(description="Whether a bigger plan would give it more at once.")


class RequestsUsageOut(Schema):
    """The requests the business has served this calendar month (UTC)."""

    this_month: int | None = Field(description="How many; None: never counted yet.")
    since: dt.date | None = Field(description="Since when they are counted, when that is after day 1; otherwise None.")


class ActivityUsageOut(Schema):
    """The people with activity in the business; the plan's places are ``people`` of the same answer."""

    active_now: int | None = Field(description="With activity in the last 5 minutes; None in a demo.")
    last_day: int | None = Field(description="Those of the last day measured; None before the first night.")
    last_day_date: dt.date | None = Field(description="That day (UTC); None before the first night.")
    last_day_is_yesterday: bool = Field(description="Whether that day is yesterday.")
    last_30_days: int | None = Field(description="Those of the 30 days it ends; None before the first night.")


class PlanUsageOut(Schema):
    """``base.plan.usage``: the plan's limits (the SaaS's photo, ``plan``) against what the business uses. A figure not
    measured yet comes as None, never as a zero."""

    #: Whether the Hub has the business's plan from erplora.com (a demo, or a business without a photo yet, has not).
    known: bool
    #: A demo: nothing of it is measured, and its data is deleted when it ends.
    demo: bool
    people: LimitOut
    devices: LimitOut
    database: DatabaseUsageOut
    files: FilesUsageOut
    connections: ConnectionsUsageOut
    requests: RequestsUsageOut
    activity: ActivityUsageOut


class UsageListIn(Schema):
    """``GET /internal/usage``: the day (UTC) the SaaS asks for, and where its last page ended."""

    day: dt.date
    cursor: UUID | None = None


class UsageRowOut(Schema):
    id: UUID
    s3_bytes: int
    db_bytes: int
    active_users_1d: int
    active_users_30d: int
    #: What the day's serving tasks counted (``control.HubActivityDaily``); null: nothing counted that day.
    requests: int | None
    peak_connections: int | None
    busy_requests: int | None


class UsageListOut(Schema):
    """One page of the day's use (saas ``hubs/README.md``, «Contrato para el Hub»)."""

    day: dt.date
    hubs: list[UsageRowOut]
    next_cursor: str | None


# ── Data: blueprints, imports and reset (APP-BASE-2) ──

#: A file uploaded in base64: 20 MB of zip (``base.blueprint.MAX_FILE_BYTES``) is 27 962 028 characters.
FILE_BASE64_MAX = 28_000_000
BlueprintPurpose = Literal["backup", "template"]
#: How a dataset of a load went: «applied», «partial», «already» (it was there), «failed», «empty» (nothing to copy)
#: or «discarded» (personal data in a template).
DatasetStatus = Literal["applied", "partial", "already", "failed", "empty", "discarded"]
#: How an app of a load went: a dataset's statuses, or «inactive» (not on here), «unknown» (this hub does not have it)
#: or «not_selected».
AppLoadStatus = Literal[
    "applied", "partial", "already", "failed", "empty", "discarded", "inactive", "unknown", "not_selected"
]
ImportStatus = Literal["complete", "partial", "failed"]


class BlueprintListIn(Schema):
    """No input: the catalogue for this person and this hub."""


class BlueprintAppOut(Schema):
    id: str
    label: str = Field(description="The app's name as the person reads it.")


class BlueprintPartOut(Schema):
    key: str = Field(description="«<app>.<what>»: a dataset, e.g. «inventory.product».")
    label: str
    rows: int


class TemplateOut(Schema):
    key: str = Field(description="«<vertical>.<language>».")
    name: str
    description: str
    language: str
    country: str = Field(description="ISO 3166 code: the country its taxes and prices are for.")
    vertical: str
    version: str
    apps: list[BlueprintAppOut] = Field(description="The apps it turns on: its vertical's.")
    contents: list[BlueprintPartOut] = Field(description="What it brings, by dataset.")


class BlueprintListOut(Schema):
    templates: list[TemplateOut] = Field(
        description="The hub's country first, then the person's language, then the hub's vertical."
    )
    empty: bool = Field(description="Nothing a template brings is in the business yet (the Home offers one).")


class BlueprintSourceIn(Schema):
    """A template of the catalogue or a .blueprint.zip of the person, exactly one of them."""

    template: str = Field(
        "", max_length=80, title=gettext_noop("Template"), description="«<vertical>.<language>» of the catalogue."
    )
    file_base64: str = Field(
        "",
        max_length=FILE_BASE64_MAX,
        title=gettext_noop("File"),
        description="A .blueprint.zip in base64 (20 MB at most).",
    )


class BlueprintDatasetOut(BlueprintPartOut):
    personal: bool = Field(description="Personal data: it travels in a backup only.")
    travels: bool = Field(description="False: it is left out of this load (personal data in a template).")


class BlueprintAppSummaryOut(BlueprintAppOut):
    status: Literal["on", "turns_on", "inactive", "unknown"] = Field(
        description="«on»; «turns_on»: off in this hub, the load turns it on first (with the apps it needs) and then "
        "loads it; «inactive»: off and left off (only its data names it, or the plan gives no right to it), nothing "
        "of it loads; «unknown»: this hub does not have it."
    )
    datasets: list[BlueprintDatasetOut]


class BlueprintSummaryOut(Schema):
    name: str
    language: str
    country: str
    purpose: BlueprintPurpose
    created_at: str = Field(description="When the file was made; empty for a template of the catalogue.")
    version: str = Field(description="The template's version; empty for a file.")
    source: Literal["catalog", "file"]
    apps: list[BlueprintAppSummaryOut]
    dropped: list[str] = Field(description="Parts of the file this hub never loads (people, fiscal data…).")


class BlueprintImportIn(BlueprintSourceIn):
    apps: list[str] | None = Field(
        None,
        max_length=200,
        title=gettext_noop("Apps to load"),
        description="The apps to load; none = every app of the blueprint.",
    )
    retry_of: UUID | None = Field(
        None,
        description="A load that did not go in whole: load again what did not, from the same template.",
        json_schema_extra=names("base.import.detail"),
    )


class DatasetLoadOut(Schema):
    key: str
    label: str
    status: DatasetStatus
    rows: int = Field(description="Rows the blueprint brings.")
    created: int
    already: int = Field(description="Rows already there: left as they were.")
    failed: int
    problems: list[str] = Field(description="What went wrong, the first ones, in the person's language.")


class AppLoadOut(Schema):
    id: str
    label: str
    status: AppLoadStatus
    reason: str = Field(
        "",
        description="Why an app of the blueprint that was off could not be turned on («inactive»), in the person's "
        "language: the plan's limit of apps, no right to it…; empty otherwise.",
    )
    datasets: list[DatasetLoadOut]


class LoadReportOut(Schema):
    status: ImportStatus
    apps: list[AppLoadOut]
    dropped: list[str]


class ImportOut(Schema):
    id: UUID
    name: str
    source: Literal["catalog", "file"]
    template_key: str
    status: ImportStatus
    created_at: dt.datetime
    created_by: str
    rows: int = Field(description="Rows it created.")
    undone: bool
    undoable: bool = Field(description="It created rows and was not undone.")
    retry: bool = Field(description="What did not go in can be loaded again.")
    retry_blocked: Literal["", "file", "version_gone", "complete", "undone"] = Field(
        description="Why it cannot be retried: «file» (uploaded by hand), «version_gone» (the template changed), "
        "«complete» (nothing missing), «undone»."
    )
    report: LoadReportOut


class ImportListIn(Schema):
    """No input: the loads of this hub, newest first."""


class ImportListOut(Schema):
    imports: list[ImportOut] = Field(description="Newest first, at most the last 50.")
    unfinished: ImportOut | None = Field(
        description="The last load, when it did not go in whole and was not undone: shown before the catalogue."
    )


class BlueprintExportIn(Schema):
    """What an export takes, flat, as a query string: the apps it registers, the ones whose data travels and, of
    those, which datasets (an app none of whose datasets is named takes all of them)."""

    name: str = Field(min_length=1, max_length=120, description="The name of the file and of the blueprint.")
    language: str = Field(min_length=2, max_length=8, description="The language of its texts (a code: «es»).")
    purpose: BlueprintPurpose = Field(
        description="«backup» (this business, its customers too) or «template» (to share: never personal data)."
    )
    apps: list[str] = Field(default_factory=list, max_length=200, description="Apps on in this hub it registers.")
    data: list[str] = Field(
        default_factory=list, max_length=200, description="Of those apps, the ones whose data travels too."
    )
    datasets: list[str] = Field(
        default_factory=list,
        max_length=200,
        description="Of those, the datasets chosen; an app none of whose datasets is named takes all.",
    )


class BlueprintFileOut(Schema):
    filename: str
    content_type: str
    content_base64: str


class DatasetListIn(Schema):
    """No input: the apps on of this hub and what of each can travel."""


class DatasetCountOut(BlueprintPartOut):
    personal: bool


class AppDatasetsOut(Schema):
    id: str
    label: str
    icon: str
    datasets: list[DatasetCountOut] = Field(description="Empty: the app travels, with nothing of its own to copy.")


class DatasetListOut(Schema):
    apps: list[AppDatasetsOut] = Field(description="By name.")


class ImportIdIn(Schema):
    """A load of this business, by its id."""

    id: UUID = Field(title=gettext_noop("Import"), json_schema_extra=names("base.import.detail"))


class ImportUndoIn(ImportIdIn):
    """A load to undo: the rows it created go."""


class RemovalOut(Schema):
    id: str
    label: str
    removed: int
    failed: int
    problems: list[str]


class ImportUndoOut(Schema):
    id: UUID
    apps: list[RemovalOut]


class HubResetIn(Schema):
    apps: list[str] = Field(default_factory=list, max_length=200, description="The sections (apps) to empty.")
    confirm: str = Field("", max_length=200, description="The business's name, typed exactly.")
    dry_run: bool = Field(False, description="True: only the plan, nothing is removed.")


class ResetDatasetOut(BlueprintPartOut):
    pass


class ResetSectionOut(Schema):
    id: str
    label: str
    rows: int
    datasets: list[ResetDatasetOut]


class HubResetOut(Schema):
    dry_run: bool
    confirm_with: str = Field(description="What to type to confirm: the business's name (its address without one).")
    available: bool = Field(
        description="False in phase 1: the business shares its database with other hubs, so nothing can be emptied."
    )
    sections: list[ResetSectionOut] = Field(description="The apps with rows: what each one would lose.")
    apps: list[RemovalOut] = Field(
        description="Always empty: the worker empties the sections after copying the data (base.hub.dumps says how it "
        "went)."
    )
    status: Literal["planned", "copying"] = Field(
        description="planned: only the plan (dry_run). copying: asked; the business's data is being copied, then the "
        "sections chosen are emptied."
    )



class HubResetApplyIn(Schema):
    """The worker's emptying of a reset it already copied (``base.hub.reset_apply``)."""

    apps: list[str] = Field(min_length=1, max_length=200, description="The sections (apps) to empty.")


class HubResetApplyOut(Schema):
    apps: list[RemovalOut] = Field(description="What was removed of each section, and what could not be.")



class HubDumpsIn(Schema):
    """No input: the copies of the business of the request."""


class ResetSectionNameOut(Schema):
    id: str
    label: str


class ResetStateOut(Schema):
    """How the last reset of the business went (``Hub.reset_sections``): asked, copying, emptying, done or failed."""

    state: Literal["copying", "emptying", "done", "failed"]
    sections: list[ResetSectionNameOut] = Field(description="The sections asked, by name.")
    requested_by: str
    error: str = Field(
        description="Why it failed: dumps_unavailable, dump_failed, emptying_failed or hub_not_ready; empty otherwise."
    )
    removed: list[RemovalOut] = Field(description="What was removed of each section (done).")
    finished_at: dt.datetime | None


class HubDumpOut(Schema):
    id: UUID
    kind: Literal["reset", "offboarding"]
    created_at: dt.datetime
    bytes: int


class HubDumpsOut(Schema):
    """``base.hub.dumps``: the copies of the business's data (newest first) and its last reset."""

    available: bool = Field(
        description="False while the business shares its database with others: no copy is ever made then."
    )
    reset: ResetStateOut | None
    dumps: list[HubDumpOut]


class HubDumpLinkIn(Schema):
    id: UUID = Field(description="The copy's id (base.hub.dumps).")


class HubDumpLinkOut(Schema):
    url: str = Field(description="A link that downloads the copy, for 15 minutes.")
    expires_at: dt.datetime


class InternalDumpOut(Schema):
    id: str = Field(description="Its key in the bucket.")
    kind: Literal["reset", "offboarding"]
    created_at: dt.datetime
    bytes: int
    url: str


class InternalDumpsOut(Schema):
    """``GET /internal/hubs/{id}/dumps`` (saas ``hubs/README.md``, «Contrato para el Hub»)."""

    available: bool
    dumps: list[InternalDumpOut]


# ── Business settings and the hub's context (APP-BASE-6) ──


class BusinessIn(Schema):
    """No input: the business of the hub this person is on."""


class BusinessOut(Schema):
    """``base.business.get``: the business as the SaaS registered it, each value named in the person's language."""

    name: str = Field(description="The business's name (on ERPlora's own hub, its issuer's legal name); empty in a demo.")
    country: str = Field(description="ISO 3166-1 alpha-2; empty in a demo. It no longer changes once the business is ready.")
    country_name: str
    timezone: str = Field(description="IANA time zone: the business's clock (the deployment's when it has none).")
    language: str = Field(description="The business's language: the one of whoever has not chosen their own.")
    language_name: str
    currency: str = Field(description="ISO 4217: the one the business's country pays in (the euro without a country).")
    currency_label: str = Field(description="«EUR · Euro»: the code and its name.")
    currency_decimals: int
    demo: bool = Field(description="A demo has no business on erplora.com: nothing to change there.")
    settings_url: str = Field(
        description="The business's settings on erplora.com, where an owner or an administrator changes its name, time "
        "zone and language; empty in a demo and on ERPlora's own hub."
    )


# ── System (APP-BASE-7) ────────────────────────────────────────────────────────────────────────────────────────


class SystemStatusIn(Schema):
    """No input: the status of the hub of the request."""


class SystemStatusOut(Schema):
    """``base.system.status``: what runs and where the business's data lives. No usage figures: one service runs every
    business, so CPU, memory and connections have no figure per business (PLAN-HUB §1a)."""

    #: The release running: its commit, short (``APP_VERSION``); ``dev`` without one (local development).
    version: str
    #: When that release was published (``APP_RELEASED_AT``); ``None`` when it is not known, never made up.
    released_at: dt.datetime | None
    #: Phase 1: every business on the one shared database; ``False`` once the hub has its own.
    shared_database: bool


class EventListIn(Schema):
    """No input: the last events between apps of the hub of the request."""


class EventLogEntryOut(Schema):
    """An event between apps as System › Logs shows it: when, how it went and where it went; never its content."""

    id: UUID
    at: dt.datetime
    level: Literal["info", "warning", "error"]
    #: The event's own name (``sale.sale.completed``).
    name: str
    #: The app that recorded it, and its name as the business knows it.
    app: str
    app_name: str
    #: What happened to it, in the person's language («Delivered to Invoicing.»).
    detail: str


class EventListOut(Schema):
    entries: list[EventLogEntryOut]


class FailedEventListIn(Schema):
    """A page of the failed events of the hub of the request, newest first."""

    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class FailedEventOut(Schema):
    """A delivery the relay gave up on: which event, from which app to which, how many attempts and the last error."""

    #: The delivery's id: what is resent or discarded.
    id: UUID
    event_id: UUID
    name: str
    source_app: str
    source_app_name: str
    target_app: str
    target_app_name: str
    attempts: int
    occurred_at: dt.datetime
    #: The start of the last error, as the app said it (it may carry a customer's data: who runs the business only).
    last_error: str
    #: ``False`` when the app it was for is no longer on in this business: resending it would fail again.
    retryable: bool


class FailedEventListOut(Schema):
    items: list[FailedEventOut]
    #: How many failed events the hub has, beyond this page.
    total: int


class FailedEventIn(Schema):
    """A failed event of the hub of the request, by its id."""

    id: UUID = Field(title=gettext_noop("Failed event"), json_schema_extra=names("base.failed_event.detail"))


class FailedEventDiscardIn(Schema):
    id: UUID = Field(title=gettext_noop("Failed event"), json_schema_extra=names("base.failed_event.detail"))
    #: Why it is discarded (optional): kept with who and when.
    reason: str = Field(default="", max_length=500)


class FailedEventOutId(Schema):
    id: UUID


class FailedEventRetryAllIn(Schema):
    """No input: every failed event of the hub of the request that can be resent."""


class FailedEventCountOut(Schema):
    #: How many failed events went back to the queue.
    count: int


# ── The way in: devices, PIN, badge, the business's dial and the person's profile (APP-BASE-3) ───────────────────


class AccessDoorIn(Schema):
    """No input: the door of the browser that asks (its device cookie), with a session or without."""


class PinPersonOut(Schema):
    id: str = Field(description="The person's way in on this hub (what a PIN entry names), never their account.")
    name: str
    initials: str


class AccessDoorOut(Schema):
    pin: bool = Field(description="Whether this browser offers the PIN pad: a shared device of the hub that asks.")
    pin_length: int = Field(description="How many digits a PIN of this business has (4 or 6).")
    people: list[PinPersonOut] = Field(description="The faces of the grid; none where the PIN is not offered.")
    wait: int = Field(description="Seconds this address still waits after too many wrong PINs; 0 when it may try.")
    plan_url: str = Field(description="erplora.com's plans, for «Upgrade plan» when another device's entry ended this one.")


class PinSetIn(Schema):
    pin: str = Field(max_length=16)
    current: str = Field(default="", max_length=16, description="The PIN it replaces, when the person has one.")


class PinSetOut(Schema):
    set: bool


class DeviceCurrentIn(Schema):
    """No input: the device of the browser that asks (its cookie)."""


class DeviceCurrentOut(Schema):
    known: bool = Field(description="Whether someone entered this hub with an account from this browser.")
    mode: Literal["shared", "personal"]
    mode_set_by: str = Field(description="Who chose the mode; empty while it is the factory one.")
    mode_set_at: dt.datetime | None


class DeviceModeIn(Schema):
    mode: Literal["shared", "personal"]


class DeviceListIn(Schema):
    """No input: every device of the hub."""


class DeviceOut(Schema):
    id: UUID
    name: str = Field(description="The one the business gave it; empty when it has none.")
    agent: str = Field(description="«Chrome · Android»: how it is recognised before it has a name.")
    mode: Literal["shared", "personal"]
    current: bool = Field(description="The one the person who asks is using.")
    in_use: bool = Field(description="It has a session open now.")
    session_until: dt.datetime | None = Field(description="When its open session ends, if it has one.")
    last_entry_at: dt.datetime
    last_user: str = Field(description="The name of whoever entered on it last.")
    created_at: dt.datetime
    unused: bool = Field(description="Nobody entered on it in 30 days and it is not the one in hand.")


class DeviceListOut(Schema):
    devices: list[DeviceOut] = Field(description="The last entered first.")
    unused: int = Field(description="How many of them «Remove the unused» would remove.")


class DeviceRenameIn(Schema):
    id: UUID = Field(title=gettext_noop("Device"), json_schema_extra=names("base.device.detail", name=DEVICE_NAMES))
    name: str = Field(max_length=80, description="«Bar», «Kitchen»: 60 characters at most once trimmed.")


class DeviceByIdIn(Schema):
    id: UUID = Field(title=gettext_noop("Device"), json_schema_extra=names("base.device.detail", name=DEVICE_NAMES))


class DeviceRemoveOut(Schema):
    removed: int
    yours: bool = Field(description="It was the device of the person who removed it: their session ended too.")


class DevicePruneIn(Schema):
    """No input: the devices nobody entered in 30 days, never the one in hand."""


class DevicePruneOut(Schema):
    removed: int


class AccessSettingsIn(Schema):
    """No input."""


class AccessSettingsOut(Schema):
    pin_policy: Literal["always", "per_shift", "never"]
    pin_inactivity_minutes: Literal[1, 5, 10, 15, 30]
    pin_length: Literal[4, 6]
    can_change: bool = Field(description="Whether the person who asks may change them (who runs the hub).")


class AccessSettingsUpdateIn(Schema):
    """Only the fields sent change (each control saves on its own); at least one."""

    pin_policy: Literal["always", "per_shift", "never"] | None = None
    pin_inactivity_minutes: Literal[1, 5, 10, 15, 30] | None = None
    pin_length: Literal[4, 6] | None = None


class ProfileIn(Schema):
    """No input: the profile is always the person's who asks."""


class ProfileOut(Schema):
    first_name: str
    last_name: str
    contact_email: str
    avatar_url: str = Field(description="Where this hub serves the photo; empty without one.")
    language: Literal["", "es", "en"] = Field(description="Empty: the business's.")
    theme_mode: Literal["", "system", "light", "dark"] = Field(description="Empty: the business's.")
    palette: str = Field(description="Empty: the business's.")
    role: str
    has_pin: bool
    pin_length: int


class ProfileUpdateIn(Schema):
    first_name: str = Field(max_length=150)
    last_name: str = Field(default="", max_length=150)
    contact_email: str = Field(default="", max_length=254)


class PreferencesIn(Schema):
    language: Literal["", "es", "en"]
    theme_mode: Literal["", "system", "light", "dark"]
    palette: Literal["", "erplora", "terracotta", "corporate", "minimal", "forest", "ocean", "violet"]


class PreferencesOut(Schema):
    language: str = Field(description="The language now in use: the person's, else the business's.")
    theme_mode: str
    palette: str


class AvatarIn(Schema):
    content_type: Literal["image/jpeg", "image/png", "image/webp"]
    # 2 MB of bytes is 2 796 204 characters of base64.
    data_base64: str = Field(max_length=2_800_000, description="The photo, in base64 (2 MB at most).")


class AvatarOut(Schema):
    avatar_url: str


class AvatarRemoveIn(Schema):
    """No input: one's own photo."""


# ── People and permissions: people, roles (APP-BASE-5) ──────────────────────────────────────────────────────────────


class PersonListIn(Schema):
    """No input: the people of the business of the request."""


class PersonWaysOut(Schema):
    """How a person gets in: the account always; at the shared tills, a PIN and a badge when the hub keeps them."""

    account: bool
    pin: bool
    badge: bool


class PersonOut(Schema):
    id: str = Field(description="The person in this hub: their account's local name (``saas:<id>``).")
    name: str
    initials: str
    email: str = Field(description="Their erplora.com address; empty for whom does not run the business.")
    role: Literal["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
    ways: PersonWaysOut
    entered: bool = Field(description="False: erplora.com names them, and they have not entered this hub yet.")
    me: bool


class SeatsOut(Schema):
    """The places of the plan the SaaS's last photo carries (``plan.max_users``; 0 is none)."""

    known: bool = Field(description="False: no photo with the plan's places yet.")
    used: int
    limit: int | None
    full: bool


class PersonListOut(Schema):
    people: list[PersonOut]
    seats: SeatsOut


class PersonIn(Schema):
    person: str = Field(
        min_length=1,
        max_length=150,
        title=gettext_noop("Person"),
        description="The ``id`` of a person of ``base.person.list``.",
        json_schema_extra=names("base.person.detail", by="person"),
    )


class PersonMayOut(Schema):
    """What who asks may change of this person's way in."""

    remove_pin: bool
    set_badge: bool


class PersonDetailOut(PersonOut):
    pin_set_at: dt.datetime | None
    badge_set_at: dt.datetime | None
    may: PersonMayOut


class BadgeSetIn(PersonIn):
    badge: str = Field(max_length=200, description="The card's number, as the reader types it (4 to 64 characters).")


class RoleListIn(Schema):
    """No input: the roles of the business of the request."""


class RoleOut(Schema):
    key: Literal["hub_owner", "hub_admin", "hub_manager", "hub_employee"]
    label: str
    origin: Literal["basic"] = Field(description="Where the role comes from: erplora.com's own four.")
    members: int
    permissions: int = Field(description="How many permissions of the apps of this deployment it gives.")


class RoleListOut(Schema):
    roles: list[RoleOut]


# ── People and permissions: the business's API keys and its API's documentation (APP-BASE-5) ──────────────────────


class ApiKeyListIn(Schema):
    """No input: the keys of the business of the request."""


class ApiKeyOut(Schema):
    id: UUID
    name: str
    prefix: str = Field(description="The token's first characters, to tell it apart; never the whole token.")
    mode: Literal["full", "read", "write", "per_app"]
    scopes: dict[str, list[Literal["read", "write"]]] = Field(description="Per app: what it may do on each app.")
    rate_per_minute: int
    created_by: str
    created_at: dt.datetime
    rotated_at: dt.datetime | None
    last_used_at: dt.datetime | None
    revoked_at: dt.datetime | None


class ApiAppOut(Schema):
    """An app this business has that publishes operations: what a key per app may be given on it."""

    id: str
    name: str
    read: bool = Field(description="It publishes queries.")
    write: bool = Field(description="It publishes commands.")


class ApiKeyListOut(Schema):
    available: bool = Field(description="False while the business shares its database with others: no key yet.")
    keys: list[ApiKeyOut]
    apps: list[ApiAppOut]


class ApiKeyCreateIn(Schema):
    name: str = Field(max_length=80)
    rate_per_minute: int = Field(60, ge=1, le=10_000)
    mode: Literal["full", "read", "write", "per_app"]
    scopes: dict[str, list[Literal["read", "write"]]] = Field(default_factory=dict)


class ApiKeyIdIn(Schema):
    id: UUID = Field(title=gettext_noop("API key"), json_schema_extra=names("base.api_key.detail"))


class ApiKeyTokenOut(Schema):
    """A key just made or rotated, with its whole token: the only time it is shown."""

    key: ApiKeyOut
    token: str


class ApiKeyRevokeOut(Schema):
    key: ApiKeyOut


# ── People and permissions: a manager's approval (APP-BASE-5) ──────────────────────────────────────────────────────


class ApprovalIn(Schema):
    """A manager approves one refused command: their person and PIN, or their badge."""

    operation: str = Field(max_length=120)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$", description="The refused request's, from requires_elevation.")
    person: str | None = Field(None, max_length=64, description="The id of who approves, from base.approval.approvers.")
    pin: str | None = Field(None, max_length=16)
    badge: str | None = Field(None, max_length=128)


class ApprovalPassOut(Schema):
    """The pass of one use (header X-Elevation-Token), shown once, and who approved."""

    token: str
    approver: str
    expires_in: int = Field(description="Seconds the pass lasts.")


class ApprovalSpendIn(Schema):
    token: str = Field(max_length=128)
    operation: str = Field(max_length=120)
    fingerprint: str = Field(max_length=64)
    figures: dict[str, Any] = Field(
        default_factory=dict, description="The figures of the request its app's sentences name, kept on the record."
    )


class ApprovalSpentOut(Schema):
    spent: bool
    id: str
    approver: str


class ApproversIn(Schema):
    operation: str = Field(max_length=120)


class ApproverOut(Schema):
    id: str = Field(description="The person's id in the hub, to approve with their PIN.")
    name: str
    initials: str


class ApproversOut(Schema):
    people: list[ApproverOut]
    pin_length: Literal[4, 6] = Field(description="Digits of the business's PIN, for the pad.")


class ApprovalListIn(Schema):
    """No input."""


class ApprovalOut(Schema):
    id: UUID
    at: dt.datetime
    action: str = Field(description="What was approved, in words, with the figures of what was done.")
    operation_label: str = Field(description="What the action is called, without figures: the «Action» filter.")
    operation: str
    requested_by: str
    approved_by: str
    way: Literal["pin", "badge"]
    used: bool
    used_at: dt.datetime | None


class ApprovalListOut(Schema):
    approvals: list[ApprovalOut]


class ApprovalExportIn(Schema):
    """What Employees › Approvals keeps on screen: its search and its filters (BASE-F85); none, the whole record."""

    search: str = Field("", max_length=200, description="Words of the action, or of who approved or who asked.")
    at_from: dt.date | None = Field(None, description="From this day, in the business's time zone.")
    at_to: dt.date | None = Field(None, description="Up to this day, included.")
    operation: str = Field("", max_length=120, description="Only the approvals of this action.")
    way: Literal["pin", "badge"] | None = Field(None, description="Only those approved with a PIN or with a badge.")
    used: bool | None = Field(None, description="Only the used ones (true) or the unused ones (false).")


class ApprovalExportOut(Schema):
    filename: str
    content_type: str
    rows: int
    csv: str


# ── People and permissions: the API's documentation (APP-BASE-5) ───────────────────────────────────────────────────


class ApiDocIn(Schema):
    """No input."""


class ApiDocOut(Schema):
    document: dict = Field(description="The OpenAPI document of what this business's apps publish.")
    apps: list[ApiAppOut] = Field(description="The apps in it (its tags), by name.")
    keys_available: bool = Field(description="Whether this business can make API keys yet.")


class ApiDocSettingsIn(Schema):
    """No input."""


class ApiDocSettingsOut(Schema):
    docs_enabled: bool
    can_change: bool = Field(description="Whether who asks may change it (who runs the business).")


class ApiDocSettingsUpdateIn(Schema):
    docs_enabled: bool


# ── Files (APP-BASE-8) ─────────────────────────────────────────────────────────────────────────────────────────

#: How the Files screen shows a file: «image», «pdf», «text», «table» (CSV, TSV), «json», «audio», «video», or «»
#: when it does not (it is downloaded).
FilePreview = Literal["image", "pdf", "text", "table", "json", "audio", "video", ""]


def file_path(title: str | None = None) -> Any:
    """A path under the business's files: names joined by «/» («Facturas/2026/marzo.pdf»); empty is the root.
    ``title`` names it on the assistant's card."""
    return Field(
        default="",
        max_length=1000,
        title=title,
        description="A path in the business's files, «Facturas/2026»; empty: the root.",
    )


FILE_PATH = file_path()
#: An upload in base64: 25 MB of file is 34 952 536 characters.
FILE_UPLOAD_BASE64_MAX = 34_952_536


class FileListIn(Schema):
    folder: str = FILE_PATH


class FileFolderOut(Schema):
    path: str
    name: str
    children: list["FileFolderOut"]


FileFolderOut.model_rebuild()


class FileCrumbOut(Schema):
    path: str
    name: str


class FileItemOut(Schema):
    path: str
    name: str
    size: int = Field(description="Bytes.")
    modified: dt.datetime | None
    #: The type the file is read with at ``base.file.read``.
    content_type: str
    preview: FilePreview


class FileSpaceOut(Schema):
    #: What the hub's files and its apps' take in the store.
    used_bytes: int
    #: The space the plan includes (the SaaS's photo); ``None``: no limit.
    limit_bytes: int | None


class FileCanOut(Schema):
    #: Upload, make folders and rename (``base.upload_files``).
    upload: bool
    #: Delete; moving takes both (``base.delete_files``).
    delete: bool


class FileListOut(Schema):
    """``base.file.list``: every folder of the business (a tree), and the files of the folder open."""

    folder: str
    #: From the root to the open folder, the root itself left out.
    crumbs: list[FileCrumbOut]
    folders: list[FileFolderOut]
    files: list[FileItemOut]
    space: FileSpaceOut
    can: FileCanOut


class FileReadIn(Schema):
    path: str = Field(max_length=1000, description="The file's path, «Facturas/marzo.pdf».")
    #: Shown in the page (``inline``) rather than downloaded, when its type is safe to show.
    inline: bool = False


class FileOut(Schema):
    path: str
    name: str
    size: int
    content_type: str
    preview: FilePreview


class FileUploadIn(Schema):
    folder: str = file_path(gettext_noop("Folder"))
    name: str = Field(max_length=1000, description="The file's name, «marzo.pdf»; a taken one becomes «marzo (1).pdf».")
    content_base64: str = Field(
        max_length=FILE_UPLOAD_BASE64_MAX, title=gettext_noop("File"), description="The file, in base64; 25 MB at most."
    )


class FileSavedOut(Schema):
    path: str
    #: The name it was kept with: the one asked for, or «name (1).ext» when that was taken.
    name: str
    size: int


class FileFolderCreateIn(Schema):
    parent: str = file_path(gettext_noop("In folder"))
    name: str = Field(max_length=1000, description="The new folder's name, «Facturas»; 100 characters at most.")


class FilePathOut(Schema):
    path: str
    name: str


class FileRenameIn(Schema):
    path: str = Field(
        max_length=1000,
        title=gettext_noop("File or folder"),
        description="The file or folder to rename, «Facturas/marzo.pdf».",
    )
    name: str = Field(max_length=1000, description="Its new name (a name, never a path), «abril.pdf».")


class FileMoveIn(Schema):
    path: str = Field(
        max_length=1000, title=gettext_noop("File or folder"), description="The file or folder to move, «marzo.pdf»."
    )
    to: str = file_path(gettext_noop("Move to"))


class FileDeleteIn(Schema):
    path: str = Field(
        max_length=1000,
        title=gettext_noop("File or folder"),
        description="The file or folder to delete, «Facturas/marzo.pdf».",
    )


class FileDeletedOut(Schema):
    path: str
    #: Whether it was a folder, deleted with everything in it.
    folder: bool


# ── Assistant (APP-BASE-9) ──────────────────────────────────────────────────────────────────────────────────────


class AssistantCallIn(Schema):
    """A tool the model asked for, as the gateway gave it: its id, its name (``demo__item__create``) and its
    arguments as the model wrote them (JSON text)."""

    call_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    arguments: str = Field(default="{}", max_length=1_000_000)


class AssistantDecisionIn(Schema):
    """The person's answer to the card of the first pending write: ``accepted``, what it typed when the card asks to
    type (a word, or how many) and ``stop`` («Cancel all»: this write and the rest of the turn)."""

    call_id: str = Field(min_length=1, max_length=200)
    accepted: bool
    typed: str = Field(default="", max_length=200)
    stop: bool = False


class AssistantTurnIn(Schema):
    """A turn of the assistant: the whole conversation (the person's browser keeps it), the tools the model asked for
    that still wait (``pending``) with their ``continuation``, the person's answer to the first one's card and whether
    the person is setting up the business (``setup``: the checklist goes to the model, read again)."""

    messages: list[dict[str, Any]] = Field(min_length=1, max_length=1000)
    continuation: str | None = Field(default=None, max_length=4096)
    pending: list[AssistantCallIn] = Field(default_factory=list, max_length=64)
    decision: AssistantDecisionIn | None = None
    setup: bool = False


class AssistantExecutedOut(Schema):
    call_id: str
    name: str = Field(description="The operation («demo.item.create»), or the tool's name when there was none.")
    app: str
    app_name: str = Field(
        description="Where it happened, in the person's language, as its card says it: the app's name, or the "
        "platform's screen («Settings»); empty when there was no operation."
    )
    screen: str = Field(
        default="",
        description="The platform's screen it happened on, by its key («settings»), for the receipt to name it in the "
        "language it is read in; empty for an app's (its menu names it).",
    )
    kind: Literal["query", "command", ""]
    outcome: Literal["ok", "error", "refused", "cancelled"]
    code: str


class AssistantMoneyOut(Schema):
    currency: str
    decimals: int


class AssistantFieldOut(Schema):
    name: str
    label: str
    kind: Literal["text", "money", "bool", "list", "object", "empty"]
    value: Any = None
    titled: bool = Field(
        default=False,
        description="Its label is the title its app wrote (a check, a table): the card calls it so over its own word "
        "for a datum it knows by its name.",
    )
    signed: bool = Field(
        default=False,
        description="An amount its app declares signed (a difference): written with its sign, «+» over.",
    )
    named: bool = Field(
        default=False,
        description="A list whose every item the server said in words (a record by its name, a moment, a value by its "
        "label, an amount): the card says its items; without it, how many it carries (`live.assistant.NAMED`).",
    )
    money: AssistantMoneyOut | None = Field(
        default=None,
        description="The currency of an amount of a preview, as its read answers it (an invoice's); none = the "
        "business's, the card's own.",
    )


class AssistantCardOut(Schema):
    operation: str
    app: str
    app_name: str
    action: str
    risk: Literal["normal", "high"]
    fields: list[AssistantFieldOut]
    count: int | None = None
    confirm_word: str = Field(description="What to type to confirm a dangerous write; empty for a normal one.")
    blocked: bool = Field(description="A dangerous write that names no record: not done from the chat.")
    money: AssistantMoneyOut | None = Field(default=None, description="The business's currency, for its amounts.")
    preview: list[AssistantFieldOut] | None = Field(
        default=None,
        description="What a dangerous write will do, as the read its app declares answers it for this person (BASE-F98); "
        "none when its app declares no preview.",
    )


class AssistantTurnOut(Schema):
    """The turn made ready (the route streams it, ``text/event-stream``): the tools' results to keep (``append``),
    what ran (``executed``), the card of the write that waits (``confirm``) with what still waits (``pending``), and
    what goes to the gateway (``messages``, ``tools``, ``instructions``, ``continuation``); ``stop``, why it goes no
    further (``assistant.too_many_steps``)."""

    messages: list[dict[str, Any]]
    append: list[dict[str, Any]]
    executed: list[AssistantExecutedOut]
    confirm: AssistantCardOut | None = None
    pending: list[AssistantCallIn]
    tools: list[dict[str, Any]]
    instructions: str
    continuation: str | None = None
    stop: str = ""


class AssistantUsageIn(Schema):
    """No input: this business's allowance of the month."""


class AssistantUsageOut(Schema):
    used: int
    limit: int = Field(description="Messages of the month in the plan; 0: the plan has no assistant.")
    resets_at: str | None = Field(None, description="When the allowance comes back (UTC); none for a demo.")
    demo: bool


#: The most excerpts of ERPlora's documentation a search returns (erplora.com's own cap, saas ASSISTANT-F28).
DOCS_SEARCH_MAX = 12


class DocsSearchIn(Schema):
    """A question about how ERPlora works, in the person's words; ``limit`` excerpts at most (up to 12)."""

    query: str = Field(min_length=1, max_length=500, description="The how-to question, in the person's words.")
    limit: int = Field(
        default=8,
        ge=1,
        description=f"How many excerpts to return, at most {DOCS_SEARCH_MAX}.",
        json_schema_extra={"maximum": DOCS_SEARCH_MAX},
    )

    @field_validator("query")
    @classmethod
    def _something_asked(cls, query: str) -> str:
        query = query.strip()
        if not query:
            raise ValueError("ask something")
        return query

    @field_validator("limit")
    @classmethod
    def _capped(cls, limit: int) -> int:
        return min(limit, DOCS_SEARCH_MAX)


class DocsExcerptOut(Schema):
    """An excerpt of ERPlora's documentation that answers, with where it comes from to cite it."""

    source: str = Field(description="Where it comes from: help, app_doc (an app's documentation), workbook or plans.")
    path: str
    heading: str = Field(description="The headings it sits under, to cite it.")
    text: str
    score: float = Field(description="How close it is to the question: 1 the same meaning, 0 nothing in common.")
    lang: str


class DocsSearchOut(Schema):
    results: list[DocsExcerptOut]


class AssistantReportIn(Schema):
    """What erplora.com's ``report`` door takes, with its limits: a long answer is reported whole."""

    message_id: str = Field(min_length=1, max_length=128)
    reason: Literal["incorrect", "harmful", "instructions", "other"]
    comment: str = Field(default="", max_length=20_000)
    question: str = Field(default="", max_length=200_000)
    answer: str = Field(min_length=1, max_length=200_000)


class AssistantReportOut(Schema):
    sent: bool
    duplicate: bool


class SupportReportIn(Schema):
    """What the person writes to erplora.com's support (BASE-F108), with the limits of erplora.com's own page
    (ACCOUNTS-F38); the account, the business and the browser go with it on their own."""

    subject: str = Field(max_length=150, title=gettext_noop("Report subject"))
    description: str = Field(max_length=5000, title=gettext_noop("What happened?"))
    #: The hub's screen the person was on, as the SPA's router knew it.
    page: str | None = Field(default=None, max_length=500, title=gettext_noop("Screen"))


class SupportReportOut(Schema):
    #: Where support answers: the account's email, as erplora.com says.
    reply_to: str


class AssistantTranscribeIn(Schema):
    # 2 MB of audio is 2 796 204 characters of base64 (the gateway's own limit).
    audio: str = Field(min_length=1, max_length=2_800_000, description="The recording, in base64.")
    mime_type: str = Field(min_length=1, max_length=100)
    language: str = Field(default="", max_length=16)


class AssistantTranscribeOut(Schema):
    text: str
    language: str


# ── Locations (round 2026-10-24b, multi-location) ──────────────────────────────────────────────────────────────────


class LocationListIn(Schema):
    """No input."""


class LocationOut(Schema):
    id: UUID
    name: str = Field(description="Its name; the default «Main» in the reader's language while it keeps that name.")
    is_default: bool = Field(description="The place the business works in unless another one is chosen.")
    is_active: bool


class LocationListOut(Schema):
    locations: list[LocationOut] = Field(description="The default first, then by name.")


# ── The shared image library (round 2026-10-30, base.image_catalog) ────────────────────────────────────────────────

from typing import Annotated  # noqa: E402

from pydantic import StringConstraints  # noqa: E402

#: A folder of the library (``hospitality``, ``beauty_hair``…).
CatalogFolder = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$", max_length=63)]


class CatalogImageSearchIn(Schema):
    query: str = Field(
        "",
        max_length=100,
        description="What the image shows, as the product or the service is called, in Spanish or English "
        "(«café con leche», «women's haircut»); empty: the whole library by title.",
    )
    folder: CatalogFolder | None = Field(
        None,
        description="Only this folder of the library: beauty_body, beauty_hair, fitness, hospitality, retail or "
        "wellness_spa.",
    )
    limit: int = Field(60, ge=1, le=100, description="How many images to return (1 to 100).")
    offset: int = Field(0, ge=0, description="How many images to skip, to read the next pages.")


class CatalogImageRefIn(Schema):
    reference: str = Field(max_length=200, description="The image's reference: catalog:<folder>/<name>.")


class CatalogImageOut(Schema):
    reference: str = Field(description="What a product or a service keeps to show it: catalog:<folder>/<name>.")
    folder: str = Field(description="Its folder of the library.")
    name: str = Field(description="Its file's name in the folder, without the extension.")
    title: str = Field(description="What it shows, in the reader's language.")
    url: str = Field(description="Where the Hub serves it.")


class CatalogImagePage(Schema):
    rows: list[CatalogImageOut] = Field(description="The images of this page, the best match first.")
    total: int = Field(description="How many images match, across every page.")
    limit: int = Field(description="The page size asked for.")
    offset: int = Field(description="The images skipped before this page.")
