"""The writes on the roles of the business. A refused command leaves no trace: no row, no event."""

import uuid

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.staff import events
from apps.staff.models import Role
from apps.staff.schemas.roles import RoleIn, RolePatchIn
from apps.staff.services.roles import update_role

from .conftest import HUB_DB, A, ctx_for, make_member, make_role, outbox, run

pytestmark = HUB_DB


# staff.role.create and staff.role.update (STAFF-F04)


def test_create_a_role():
    role = run(
        "staff.role.create",
        RoleIn(name="Stylist", description="Cuts", color="#123456", order=3),
    )
    assert (
        role.name,
        role.description,
        role.color,
        role.order,
        role.member_count,
        role.is_active,
    ) == (
        "Stylist",
        "Cuts",
        "#123456",
        3,
        0,
        True,
    )
    assert outbox() == [(events.ROLE_CREATED, A.key, {"id": str(role.id)})]


def test_a_role_name_is_not_repeated():
    make_role("Stylist")
    with pytest.raises(Conflict) as excinfo:
        run("staff.role.create", RoleIn(name="STYLIST"))
    assert excinfo.value.code == "staff.role_name_taken"
    assert Role.objects.count() == 1 and outbox() == []


def test_update_and_retire_a_role():
    role = make_role("Stylist")
    make_member(role=role)
    updated = run(
        "staff.role.update",
        RolePatchIn(id=role.id, name="Senior stylist", is_active=False),
    )
    assert (updated.name, updated.is_active, updated.member_count) == (
        "Senior stylist",
        False,
        1,
    )
    assert outbox() == [(events.ROLE_UPDATED, A.key, {"id": str(role.id)})]


def test_role_update_rules():
    role, other = make_role("Stylist"), make_role("Barber")
    with pytest.raises(Conflict):
        run("staff.role.update", RolePatchIn(id=other.id, name="stylist"))
    run(
        "staff.role.update", RolePatchIn(id=role.id, name="Stylist")
    )  # no change, no event
    with pytest.raises(NotFound):
        run("staff.role.update", RolePatchIn(id=uuid.uuid7(), name="x"))
    assert outbox() == []


def test_an_employee_does_not_manage_roles():
    with pytest.raises(PermissionDenied):
        run("staff.role.create", RoleIn(name="x"), "hub_employee")
    with pytest.raises(PermissionDenied):
        update_role(ctx_for("hub_employee"), RolePatchIn(id=make_role().id, name="x"))
