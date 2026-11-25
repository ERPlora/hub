"""Whose working day a command acts on, and the forgotten day the commands refuse to close or pause."""

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.attendance.models import Record
from apps.staff.models import Member

from .conftest import HUB_DB, ctx_for, make_member, refused, run

pytestmark = HUB_DB


# Clocking someone else (ATTENDANCE-F12)


def test_a_manager_clocks_ana_in_and_out_by_name(person, clock, make_user):
    clock("2026-10-06T07:00")
    ana, _ = person()
    boss = make_user("boss", role="hub_manager")
    manager = ctx_for("hub_manager", actor=boss)
    run("attendance.record.clock_in", {"member": "ana"}, manager)
    day = Record.objects.get()
    assert (day.member, day.created_by) == (ana, boss.person)
    clock("2026-10-06T15:00")
    run("attendance.break.start", {"member_id": str(ana.id)}, manager)
    run("attendance.record.clock_out", {"member": "Ana López"}, manager)
    day.refresh_from_db()
    assert (day.status, day.updated_by) == ("closed", boss.person)


def test_an_employee_cannot_clock_someone_else(person, clock):
    clock("2026-10-06T07:00")
    _, ctx = person()
    person("Bea", "Ruiz")
    with pytest.raises(PermissionDenied):
        run("attendance.record.clock_in", {"member": "Bea"}, ctx)
    # Naming themselves is fine.
    run("attendance.record.clock_in", {"member": "Ana"}, ctx)
    assert Record.objects.get().member.first_name == "Ana"


def test_naming_someone_who_is_not_there(person, clock):
    clock("2026-10-06T07:00")
    person()
    person("Ana", "Ruiz")
    make_member("Carlos", "Gil", status=Member.Status.TERMINATED)
    with pytest.raises(Conflict) as caught:
        run("attendance.record.clock_in", {"member": "Ana"}, ctx_for())
    assert (
        caught.value.code == "attendance.ambiguous_member"
        and "Ana López" in caught.value.message
    )
    for name in ("Nadie", "Carlos"):
        with pytest.raises(NotFound):
            run("attendance.record.clock_in", {"member": name}, ctx_for())



# A forgotten day is not closed as a 24-hour day: it waits for a manager's correction. The
# commands judge it themselves, without waiting for the worker's review.


@pytest.mark.parametrize("name", ["attendance.record.clock_out", "attendance.break.start", "attendance.break.end"])
def test_a_forgotten_day_is_not_clocked_out_nor_paused_the_next_morning(person, clock, name):
    clock("2026-10-05T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T07:00")
    error = refused("attendance.day_needs_review", name, {}, ctx)
    assert "waiting for review" in error.message
    assert Record.objects.get().clock_out_at is None


def test_within_the_hours_a_long_day_still_clocks_out(person, clock):
    clock("2026-10-05T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-05T18:59")
    assert run("attendance.record.clock_out", {}, ctx).status == "closed"

