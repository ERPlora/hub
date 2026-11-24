"""The catalogue of roles with their active members, and the role a new member would take (STAFF-F01, F04, F23)."""

import pytest
from live.errors import InvalidPayload, PermissionDenied
from live.operations import get

from apps.staff.models import Member
from apps.staff.queries.roles import ROLE_UNAVAILABLE
from apps.staff.schemas.roles import RoleListIn

from .conftest import HUB_DB, TERMINATED, ctx_for, make_member, make_role, run

pytestmark = HUB_DB


# staff.role.list (STAFF-F04, STAFF-F23)


def test_positions_with_their_active_members():
    stylist, barber = (
        make_role("Stylist", description="Cuts and colour", color="#ff0000"),
        make_role("Barber"),
    )
    make_member("Ana", role=stylist)
    make_member("Bea", role=stylist, status=Member.Status.ON_LEAVE)
    make_member("Carla", role=stylist, status=TERMINATED)
    retired = make_role("Washer", is_active=False)

    page = run("staff.role.list", RoleListIn(), "hub_employee")

    assert [(row.name, row.member_count, row.is_active) for row in page.rows] == [
        ("Barber", 0, True),
        ("Stylist", 1, True),
        ("Washer", 0, False),
    ]
    assert (page.rows[1].description, page.rows[1].color) == (
        "Cuts and colour",
        "#ff0000",
    )
    assert [
        row.id for row in run("staff.role.list", RoleListIn(is_active=False)).rows
    ] == [retired.id]
    assert [
        row.id for row in run("staff.role.list", RoleListIn(search="COLOUR")).rows
    ] == [stylist.id]
    assert [
        row.id for row in run("staff.role.list", RoleListIn(search="barb")).rows
    ] == [barber.id]


def test_roles_carry_their_order_and_sort_and_filter_like_the_old_table():
    stylist = make_role("Stylist", color="#ff0000", order=2)
    barber = make_role("Barber", order=1)
    make_member("Ana", role=stylist)
    make_member("Bea", role=stylist)
    make_member("Carla", role=barber)

    def names(**params):
        return [row.name for row in run("staff.role.list", RoleListIn(**params)).rows]

    assert [row.order for row in run("staff.role.list", RoleListIn()).rows] == [1, 2]
    assert names(sort="-member_count") == ["Stylist", "Barber"]
    assert names(sort="order") == ["Barber", "Stylist"]
    assert names(sort="-name") == ["Stylist", "Barber"]
    assert names(color="#FF0000") == ["Stylist"]
    assert names(member_count_min=2) == ["Stylist"]
    assert names(member_count_max=1) == ["Barber"]


# staff.role.resolve (STAFF-F01, hub#538): the role a new member would take, checked before the assistant's card


def resolve(as_role="hub_admin", **data):
    op = get("staff.role.resolve")
    return op(ctx_for(as_role), op.input.model_validate(data))


def test_a_role_resolves_to_the_active_one_by_its_name_in_any_case_or_by_its_id():
    cashier = make_role("Cajero")
    assert resolve(role="cajero").model_dump() == {"id": cashier.id, "name": "Cajero"}
    assert resolve(role_id=str(cashier.id)).model_dump() == {"id": cashier.id, "name": "Cajero"}
    assert resolve().model_dump() == {"id": None, "name": None}


@pytest.mark.parametrize(
    ("data", "field"),
    [
        ({"role": "cajero"}, "role"),
        ({"role": "Retired"}, "role"),
        ({"role_id": "0190a3b4-0000-7000-8000-000000000000"}, "role_id"),
        ({"role_id": "retired"}, "role_id"),
    ],
    ids=["a-name-it-does-not-have", "a-retired-name", "an-id-it-does-not-have", "a-retired-id"],
)
def test_a_role_the_business_does_not_have_is_refused_on_its_datum(data, field):
    """The refusal the write itself gives (``InvalidPayload`` on ``role`` or ``role_id``), with the screen's words."""
    retired = make_role("Retired", is_active=False)
    if data.get("role_id") == "retired":
        data = {"role_id": str(retired.id)}
    with pytest.raises(InvalidPayload) as refused:
        resolve(**data)
    assert set(refused.value.fields) == {field}
    assert refused.value.fields[field] == str(ROLE_UNAVAILABLE)


def test_only_who_may_add_a_member_resolves_its_role():
    make_role("Cajero")
    with pytest.raises(PermissionDenied):
        resolve(as_role="hub_employee", role="Cajero")
    assert resolve(as_role="hub_manager", role="Cajero").name == "Cajero"
