"""Schemas of the sessions the SaaS opens and of the business's users (``base.session.*``, ``base.hub_user.*``).
``SessionMeOut`` mirrors ``SessionMe`` of packages/ui (shell/session.ts)."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field

from base.schemas.hub_registry import MemberIn


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
    # (base.activation); "activating" while the hub's own database gets its tables.
    state: Literal["on", "activating", "off"]


class SessionDemo(Schema):
    """The demo the session is in: when it ends (the shell's banner)."""

    expires_at: dt.datetime


class SessionAccessIn(Schema):
    pass


class SessionAccessOut(Schema):
    """A fingerprint of what the session may do: it changes exactly when its permissions do."""

    key: str


class SessionMeOut(Schema):
    user: SessionUser | None
    scope: SessionScope
    permissions: list[str]
    menu: list[MenuGroup]
    apps: list[AppState]
    #: Per app, the paths of the menu entries this person may not open: the router's gate says «No access» on them.
    locked: dict[str, list[str]]
    language: str
    #: Always there; ``None`` on a business's hub.
    demo: SessionDemo | None


class GrantorsIn(Schema):
    pass


class Grantor(Schema):
    name: str


class GrantorsOut(Schema):
    """Who can give this person a screen it may not open: by name only, never how to reach them."""

    grantors: list[Grantor]


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

