"""Attendance against the real Staff app (``requires = ["staff"]``), through Staff's own operations and
events, never a double: the staff record a manager creates and links is the one that clocks; renaming,
unlinking, deactivating and terminating it in Staff reach the time clock as the WORKBOOK says."""

import pytest
from live.models import OutboxEvent

from apps.attendance import events
from apps.attendance.models import Correction, Record
from apps.staff.models import Member

from .conftest import A, ctx_for, run

pytestmark = pytest.mark.django_db


@pytest.fixture
def ana(make_user, clock):
    """Ana's account and the staff record a manager creates and links in Staff (STAFF-F01, F03)."""
    clock("2026-10-06T07:00")
    user = make_user("ana", role="hub_employee", first_name="Ana", last_name="López")
    member = run(
        "staff.member.create",
        {"first_name": "Ana", "last_name": "López", "user_id": user.pk},
        ctx_for("hub_manager"),
    )
    return user, member.id, ctx_for("hub_employee", actor=user)


def staff_event(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).latest("created_at").payload


def test_the_record_staff_links_is_the_one_that_clocks(ana, clock):
    _, member_id, ctx = ana
    day = run("attendance.record.clock_in", {}, ctx)
    assert day.member_id == member_id and day.member_name == "Ana López"
    assert run("attendance.record.current", {}, ctx).member.id == member_id


def test_a_rename_in_staff_shows_in_the_time_clock(ana):
    _, member_id, ctx = ana
    run("attendance.record.clock_in", {}, ctx)
    run(
        "staff.member.update",
        {"id": str(member_id), "last_name": "López Gil"},
        ctx_for("hub_manager"),
    )
    assert run("attendance.record.list", {}, ctx).rows[0].member_name == "Ana López Gil"
    assert (
        run("attendance.presence.list", {}, ctx_for("hub_manager")).rows[0].member_name
        == "Ana López Gil"
    )


def test_unlinking_the_account_in_staff_stops_the_clock(ana):
    _, member_id, ctx = ana
    run(
        "staff.member.update",
        {"id": str(member_id), "user_id": None},
        ctx_for("hub_manager"),
    )
    with pytest.raises(Exception) as caught:
        run("attendance.record.clock_in", {}, ctx)
    assert getattr(caught.value, "code", "") == "attendance.no_member_record"
    assert run("attendance.record.current", {}, ctx).member is None


def test_a_deactivated_record_cannot_clock_in_but_still_clocks_out(ana, clock):
    _, member_id, ctx = ana
    run("attendance.record.clock_in", {}, ctx)
    run("staff.member.deactivate", {"id": str(member_id)}, ctx_for("hub_admin"))
    clock("2026-10-06T15:00")
    assert run("attendance.record.clock_out", {}, ctx).status == "closed"
    clock("2026-10-07T07:00")
    with pytest.raises(Exception) as caught:
        run("attendance.record.clock_in", {}, ctx)
    assert getattr(caught.value, "code", "") == "attendance.member_not_active"


def test_terminating_in_staff_closes_the_open_day(ana, clock):
    # ATTENDANCE-F13: Staff's event, handed to this app's reaction directly (the worker's relay hands it
    # over in tests/test_relay.py).
    _, member_id, ctx = ana
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T11:00")
    run("attendance.break.start", {}, ctx)
    clock("2026-10-06T12:00")
    run(
        "staff.member.terminate",
        {"id": str(member_id), "reason": "End of contract"},
        ctx_for("hub_admin"),
    )

    closed = events.react(
        A, events.MEMBER_TERMINATED, staff_event(events.MEMBER_TERMINATED)
    )

    assert closed.record.status == "closed" and closed.record.break_seconds == 3600
    assert (
        Correction.objects.get().reason
        == "Day closed when the person was terminated in Staff."
    )
    # The days stay four years and keep their name; the person no longer clocks.
    assert (
        run(
            "attendance.record.list",
            {"member_id": str(member_id)},
            ctx_for("hub_manager"),
        )
        .rows[0]
        .member_name
        == "Ana López"
    )
    assert run("attendance.record.current", {}, ctx).member is None
    # A repeated delivery changes nothing.
    assert (
        events.react(
            A, events.MEMBER_TERMINATED, staff_event(events.MEMBER_TERMINATED)
        ).record
        is None
    )
    assert Correction.objects.count() == 1


def test_a_rehired_person_keeps_seeing_their_old_days(ana, clock):
    user, member_id, ctx = ana
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T15:00")
    run("attendance.record.clock_out", {}, ctx)
    run("staff.member.terminate", {"id": str(member_id)}, ctx_for("hub_admin"))
    # Staff frees the account on termination: a new record can hang from it.
    again = run(
        "staff.member.create",
        {"first_name": "Ana", "last_name": "López", "user_id": user.pk},
        ctx_for("hub_manager"),
    )
    clock("2026-11-02T07:00")
    run("attendance.record.clock_in", {}, ctx)
    mine = run("attendance.record.list", {"mine": True}, ctx)
    assert {row.member_id for row in mine.rows} == {member_id, again.id}
    assert Member.objects.filter(user=user).count() == 2
    assert Record.objects.count() == 2


def test_the_person_filter_offers_staff_records(ana):
    _, member_id, _ = ana
    run(
        "staff.member.create",
        {"first_name": "Bea", "last_name": "Ruiz"},
        ctx_for("hub_manager"),
    )
    people = run("attendance.person.list", {}, ctx_for("hub_manager"))
    assert [p.name for p in people.rows] == ["Ana López", "Bea Ruiz"]
    assert people.rows[0].id == member_id
