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


class HubStateIn(Schema):
    """``PUT /internal/hubs/{id}/state``: the SaaS's photo (``photo``, as it came) and the parts the Hub applies."""

    id: UUID
    version: int = Field(ge=0)
    status: Literal["active", "past_due", "suspended"] | None = None
    verifactu: dict[str, Any] | None = None
    photo: dict[str, Any]


class HubStateOut(Schema):
    applied: bool
    version: int


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
