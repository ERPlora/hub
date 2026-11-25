"""Schemas of the business's roles (``base.role.*``): the basic ones of erplora.com and the business's own."""

from typing import Annotated, Literal

from django.utils.translation import gettext_noop
from ninja import Schema
from pydantic import Field

from base.schemas.assistant import names
from base.schemas.people import PersonIn

#: What a role does with a permission, as ``base.roles`` keeps it.
State = Literal["on", "approval", "off"]
Name = Annotated[str, Field(max_length=80, title=gettext_noop("Name"))]
Description = Annotated[str, Field(max_length=500, title=gettext_noop("Description"))]
STATE = (
    "on: the role does it; approval: only if a manager approves it there and then with their PIN; off: not at all."
)
ROLE_SAID = "A role's key, from base.role.list: hub_owner, hub_admin, hub_manager… for a basic one, an id for the business's own."
#: The mark of a datum that names a role, for the assistant's card to call it as its list does.
NAMED = names("base.role.detail", by="role", name=("label",))


class RoleListIn(Schema):
    """No input: the roles of the business of the request."""


class RoleOut(Schema):
    key: str = Field(description="A basic role as erplora.com names it (hub_owner…); the business's own, its id.")
    label: str
    description: str
    origin: Literal["basic", "own"] = Field(description="Where the role comes from: erplora.com or this business.")
    members: int = Field(
        title=gettext_noop("People with this role"), description="How many people of the business have it."
    )
    to_review: bool = Field(
        description="The business's own: an app turned on or a permission added after it was saved is still to look at."
    )


class RoleRowOut(RoleOut):
    permissions: int = Field(description="How many permissions of the apps of this deployment it gives.")


class RoleListOut(Schema):
    roles: list[RoleRowOut]


class RoleIn(Schema):
    role: str = Field(title=gettext_noop("Role"), description=ROLE_SAID, json_schema_extra=NAMED)


class RolePermissionOut(Schema):
    permission: str
    phrase: str = Field(description="What the permission lets a person do, in business words and the reader's language.")
    state: State = Field(description=STATE)
    approvable: bool = Field(description="A manager can approve it there and then, so a role may leave it to approval.")
    to_review: bool = Field(description="The business's own: the role was saved before this permission was there to look at.")


class RoleAppOut(Schema):
    app: str = Field(description="The app's label; «base» for the business itself and «sensitive» for the sensitive data.")
    name: str
    permissions: list[RolePermissionOut]


class RoleDetailOut(RoleOut):
    apps: list[RoleAppOut] = Field(description="The business first, each app that is on by its name, the sensitive data last.")


class RoleCreateIn(Schema):
    based_on: str = Field(title=gettext_noop("Based on"), description=ROLE_SAID, json_schema_extra=NAMED)
    name: Name
    description: Description = ""


class RoleUpdateIn(RoleIn):
    name: Name | None = None
    description: Description | None = None
    states: dict[str, State] | None = Field(
        None,
        title=gettext_noop("What it allows"),
        description=f"The permissions that change, by their name in base.role.detail, each with what it becomes. {STATE}",
    )


class RoleDeleteOut(Schema):
    key: str


class RoleAssignIn(PersonIn):
    role: str = Field(
        title=gettext_noop("Role"),
        description=(
            "The id of a role of the business (base.role.list) to give it to the person; the role of their invitation "
            "(``role`` in base.person.list) to return them to it. Any other basic role is given on erplora.com."
        ),
        json_schema_extra=NAMED,
    )


class RoleAssignOut(Schema):
    person: str = Field(description="The ``id`` of the person in base.person.list.")
    name: str
    role: str = Field(description="The key of the role they have now, as base.role.list names it.")
    label: str = Field(description="Its name.")
