"""Schemas of the roles: their list, writing one, and the one a staff member would take."""

from uuid import UUID

from ninja import Field, Schema

from apps.staff.schemas.fields import (
    A_ROLE,
    D_ROLE,
    D_ROLE_ID,
    ROLE,
    Color,
    Name,
    Page,
    PageIn,
    Search,
    Text100,
    Text500,
    _both_ways,
)

#: The largest role order the database column (a 4-byte integer) holds.
MAX_ORDER = 2_147_483_647

ROLE_SORTS = (
    "name",
    "description",
    "color",
    "order",
    "is_active",
    "member_count",
    "id",
)

RoleSort = _both_ways(ROLE_SORTS)


class RoleListIn(PageIn):
    search: Search | None = Field(
        None, description="Text to look for in the name or the description."
    )
    is_active: bool | None = Field(
        None, description="Keep only the active (true) or the retired (false) roles."
    )
    color: Color | None = Field(
        None, description="Keep the roles with this colour (#RRGGBB)."
    )
    member_count_min: int | None = Field(
        None, ge=0, description="Keep the roles with at least this many active people."
    )
    member_count_max: int | None = Field(
        None, ge=0, description="Keep the roles with at most this many active people."
    )
    sort: RoleSort = Field(
        "name", description="Column to sort by; a leading '-' sorts descending."
    )


class RoleIn(Schema):
    name: Name = Field(
        description="Name of the role, unique in the business (e.g. «Stylist»)."
    )
    description: Text500 = Field("", description="What the role does (optional).")
    color: Color = Field("", description="Colour as #RRGGBB; empty for none.")
    order: int = Field(0, ge=0, le=MAX_ORDER, description="Position among the roles (0 first).")


class RolePatchIn(Schema):
    """Only the fields sent are changed; ``null`` leaves a field as it is."""

    id: UUID = Field(title=ROLE, description="The role's id.", json_schema_extra=A_ROLE)
    name: Name | None = Field(None, description="New name.")
    description: Text500 | None = Field(None, description="New description.")
    color: Color | None = Field(None, description="New colour as #RRGGBB.")
    order: int | None = Field(None, ge=0, le=MAX_ORDER, description="New position among the roles.")
    is_active: bool | None = Field(
        None,
        description="false retires the role (no longer offered); true brings it back.",
    )


class RoleOut(Schema):
    id: UUID
    name: str
    description: str
    color: str
    order: int
    is_active: bool
    member_count: int = Field(description="Active people with this role.")


class RoleResolveIn(Schema):
    """The role a member would take, as staff.member.create takes it: by id or by name."""

    role_id: UUID | None = Field(None, description=D_ROLE_ID)
    role: Text100 | None = Field(None, description=D_ROLE)


class RoleResolveOut(Schema):
    id: UUID | None = Field(description="The role's id; none when no role was given.")
    name: str | None = Field(description="The role's name; none when no role was given.")


RolePage = Page[RoleOut]
