"""The directory's filters as staff.member.list applies them: a filter left out or empty keeps every record, «not
bookable» keeps the not bookable ones, and a role by name is that very role, not one whose name contains it."""

from live.operations import get

from apps.staff.schemas.members import MemberListIn

from .conftest import HUB_DB, ctx_for, make_member, make_role

pytestmark = HUB_DB


def names(**params) -> list[str]:
    page = get("staff.member.list")(ctx_for("hub_admin"), MemberListIn(**params))
    return [row.first_name for row in page.rows]


def test_an_empty_filter_keeps_every_record():
    stylist = make_role("Stylist")
    make_member("Ana", role=stylist, color="#ff0000")
    make_member("Bea")
    assert names(first_name="", email="", color="", role_name="") == ["Ana", "Bea"]


def test_not_bookable_keeps_only_the_not_bookable():
    make_member("Ana")
    make_member("Bea", is_bookable=False)
    assert (names(is_bookable=False), names(is_bookable=True)) == (["Bea"], ["Ana"])


def test_a_role_by_name_is_that_role_and_not_one_whose_name_contains_it():
    make_member("Ana", role=make_role("Stylist"))
    make_member("Bea", role=make_role("Senior stylist"))
    assert (names(role_name="STYLIST"), names(role_name="styl")) == (["Ana"], [])
