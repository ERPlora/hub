"""The people of the «Person» filter (attendance.person.list) and one of them by id (attendance.person.detail): who left
is listed while they have days, and an employee reads only their own person."""

import pytest
from live.errors import NotFound, PermissionDenied

from apps.attendance.schemas import PersonOut, PersonPage
from apps.staff.models import Member

from .conftest import HUB_DB, ctx_for, day, make_member, run

pytestmark = HUB_DB


# attendance.person.list: the «Person» filter


def test_the_people_of_the_filter_include_who_left_with_days(person):
    person()
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    make_member(
        "Dora", "Sin", status=Member.Status.TERMINATED
    )  # left without a single day
    day(gone, "2026-09-01T07:00", "2026-09-01T15:00")
    page = run("attendance.person.list", {}, ctx_for("hub_manager"))
    assert isinstance(page, PersonPage)
    assert [(p.name, p.status) for p in page.rows] == [
        ("Ana López", "active"),
        ("Carlos Gil", "terminated"),
    ]
    assert [
        p.name
        for p in run(
            "attendance.person.list", {"search": "gil"}, ctx_for("hub_manager")
        ).rows
    ] == ["Carlos Gil"]


# attendance.person.detail: one person by id, as the «Person» filter shows them (the assistant's card names by it)


def test_an_employee_reads_their_own_person_by_its_id(person):
    ana, ctx = person()
    found = run("attendance.person.detail", {"id": str(ana.id)}, ctx)
    assert isinstance(found, PersonOut)
    assert (found.id, found.name, found.status) == (ana.id, "Ana López", "active")


def test_someone_else_does_not_exist_for_an_employee(person):
    _, ctx = person()
    bea = make_member("Bea", "Ruiz")
    with pytest.raises(NotFound):
        run("attendance.person.detail", {"id": str(bea.id)}, ctx)


@pytest.mark.parametrize(
    "extra", ["attendance.view_all", "attendance.clock_others", "attendance.correct"]
)
def test_who_sees_the_team_clocks_others_or_corrects_reads_anyone(extra):
    bea = make_member("Bea", "Ruiz")
    ctx = ctx_for(permissions={"attendance.clock", extra})
    assert run("attendance.person.detail", {"id": str(bea.id)}, ctx).name == "Bea Ruiz"


def test_who_left_is_read_while_they_have_days_as_the_filter_lists_them():
    gone = make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    nobody = make_member("Dora", "Sin", status=Member.Status.TERMINATED)
    day(gone, "2026-09-01T07:00", "2026-09-01T15:00")
    found = run("attendance.person.detail", {"id": str(gone.id)}, ctx_for("hub_manager"))
    assert (found.name, found.status) == ("Carlos Gil", "terminated")
    for missing in (nobody.id, "0192f0b2-3333-7000-8000-000000000003"):
        with pytest.raises(NotFound):
            run("attendance.person.detail", {"id": str(missing)}, ctx_for("hub_manager"))


def test_a_person_needs_the_time_clock():
    bea = make_member("Bea", "Ruiz")
    with pytest.raises(PermissionDenied):
        run("attendance.person.detail", {"id": str(bea.id)}, ctx_for(permissions={"staff.view"}))


def test_nobody_behind_the_request_reads_no_person():
    """«Clock in» alone with no account behind it (the platform, an anonymous caller): there is no own record to read,
    so nobody is named — never anyone."""
    bea = make_member("Bea", "Ruiz")
    with pytest.raises(NotFound):
        run("attendance.person.detail", {"id": str(bea.id)}, ctx_for(actor=None, permissions={"attendance.clock"}))
