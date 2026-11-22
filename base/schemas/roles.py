"""Schemas of «What it allows» of a basic role (``base.role.detail``)."""

from typing import Literal

from ninja import Field, Schema

from base.schemas.people import HubRole


class RoleDetailIn(Schema):
    role: str = Field(description="The basic role, as erplora.com names it: hub_owner, hub_admin, hub_manager…")


class RolePermissionOut(Schema):
    permission: str
    phrase: str = Field(description="What the permission lets a person do, in business words and the reader's language.")
    state: Literal["yes", "approval", "no"] = Field(
        description="yes: the role holds it; approval: a manager approves it there and then with their PIN; no: not at all."
    )


class RoleAppOut(Schema):
    app: str = Field(description="The app's label; «base» for the business itself and «sensitive» for the sensitive data.")
    name: str
    permissions: list[RolePermissionOut]


class RoleDetailOut(Schema):
    key: HubRole
    label: str
    origin: Literal["basic"] = Field(description="Where the role comes from: erplora.com's own.")
    members: int = Field(description="How many people of the business have it.")
    apps: list[RoleAppOut] = Field(description="The business first, each app that is on by its name, the sensitive data last.")
