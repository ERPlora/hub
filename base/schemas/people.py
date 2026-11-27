"""Schemas of the business's people (``base.person.*``)."""

import datetime as dt
from typing import Literal

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field

from base import people as people_rules
from base.models import Membership
from base.schemas.assistant import names
from base.sensitive import TEAM_CONTACT


# ── People and permissions: people ──────────────────────────────────────────────────────────────────────────────────

#: erplora.com's roles of a business, as its photo and its login send them.
HubRole = Literal[*Membership.Role.values]


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
    email: str | None = Field(
        description="Their erplora.com address; null for whoever does not see the team's contact details.",
        json_schema_extra=TEAM_CONTACT,
    )
    role: HubRole
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
    """What who asks may change of this person's way in and of their role in this business."""

    remove_pin: bool
    set_badge: bool
    give_role: bool = Field(
        description="Who asks may give them a role of the business, or return them to their invitation's."
    )


#: Why who asks, managing roles, may not give a person a role (the codes of ``base.role.assign``).
RoleRefusal = Literal[*people_rules.ROLE_REFUSALS]


class PersonDetailOut(PersonOut):
    pin_set_at: dt.datetime | None
    badge_set_at: dt.datetime | None
    business_role: str | None = Field(
        description=(
            "The id of the role of the business that rules what they may do (base.role.list); null: their invitation's."
        )
    )
    role_refusal: RoleRefusal | None = Field(
        description="Why who asks may not give them a role; null when they may, or when who asks does not manage roles."
    )
    may: PersonMayOut


class BadgeSetIn(PersonIn):
    badge: str = Field(max_length=200, description="The card's number, as the reader types it (4 to 64 characters).")

