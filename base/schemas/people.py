"""Schemas of the business's people (``base.person.*``) and roles (``base.role.list``)."""

import datetime as dt
from typing import Literal

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field

from base.schemas.assistant import names


# ── People and permissions: people, roles ───────────────────────────────────────────────────────────────────────────


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

