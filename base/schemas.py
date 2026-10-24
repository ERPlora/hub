"""Schemas of base's operations. ``SessionMeOut`` mirrors ``SessionMe`` of packages/ui (shell/session.ts).

The registry's (``Hub…``) are the bodies of the SaaS's ``/internal/hubs/{id}`` calls (plan 2026-10-17, §1.5):
``HubRegistryIn`` is ``hubs.queries.hub_registry`` of the SaaS, ``HubOut`` what the Hub answers to it. The demos'
(``Demo…``) are those of ``POST /internal/demos`` and ``POST /internal/demos/{slug}/codes``, as the SaaS's
``hubs.hub_client.create_demo`` and ``create_demo_code`` send and read them.
"""

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field


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
    # Phase 1: every installed app is "on"; activation per hub comes in phase 2.
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


class HubSeedLocalIn(Schema):
    """``manage.py seed_local_hubs``: the local hubs to leave ready (``a`` and ``b``)."""

    slugs: list[str]


class SeededHub(Schema):
    slug: str
    outcome: Literal["created", "ready_again", "already_ready"]


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
    """The browser's demo; ``created`` says whether this call made it (201) or it was the live one (200)."""

    id: UUID
    slug: str
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
    #: ``on``, or ``blocked`` while the business has no right to it (phase 2 adds turned off, activating, failed).
    state: Literal["on", "blocked"]
    #: The first screen of its menu this person may open; ``None``: «Open» is not offered.
    path: str | None
    #: What it needs, transitively (it comes along with it), and the apps that need it.
    requires: list[str]
    required_by: list[str]


class AppListOut(Schema):
    apps: list[AppOut]
    #: erplora.com's Store of this business's modules, where a paid one is bought (never inside the Hub).
    store_url: str


class PlanUsageIn(Schema):
    """No input: the plan of the business of the request."""


class LimitOut(Schema):
    #: How much is in use; ``None`` when the Hub does not count it (never a made-up figure).
    used: int | None
    #: The plan's limit; ``None`` when it has none (0 in the SaaS's plan) or the plan is not known.
    limit: int | None


class PlanUsageOut(Schema):
    """``base.plan.usage``: the plan's limits (the SaaS's photo, ``plan``) against what the business uses."""

    #: Whether the Hub has the business's plan from erplora.com (a demo, or a business without a photo yet, has not).
    known: bool
    people: LimitOut
    devices: LimitOut

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
    id: UUID
    name: str = Field(max_length=80, description="«Bar», «Kitchen»: 60 characters at most once trimmed.")


class DeviceByIdIn(Schema):
    id: UUID


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
