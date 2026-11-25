"""Clocking in: attendance.record.clock_in, its guards and the forgotten day it flags on the way."""

import datetime as dt

import pytest

from apps.attendance import events
from apps.attendance.models import AttendanceSettings, Record
from apps.attendance.schemas import RecordOut
from apps.staff.models import Member

from .conftest import HUB_DB, ctx_for, names, outbox, refused, run

pytestmark = HUB_DB


# attendance.record.clock_in (ATTENDANCE-F01)


def test_clocking_in_opens_my_day_at_the_servers_time(person, clock):
    now = clock("2026-10-06T07:00")
    ana, ctx = person()
    result = run("attendance.record.clock_in", {}, ctx)
    assert isinstance(result, RecordOut)
    day = Record.objects.get()
    assert (result.id, day.member, day.status, day.source) == (
        day.id,
        ana,
        "open",
        "shared",
    )
    assert (day.clock_in_at, day.work_date, day.created_by) == (
        now,
        dt.date(2026, 10, 6),
        ctx.actor.person,
    )
    assert (day.in_lat, day.in_distance_m, day.in_within_radius) == (None, None, None)
    assert outbox() == [
        (events.CLOCKED_IN, {"id": str(day.id), "member_id": str(ana.id)})
    ]


def test_a_second_clock_in_while_a_day_is_open_is_refused(person, clock):
    clock("2026-10-06T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T07:05")
    error = refused(
        "attendance.already_clocked_in", "attendance.record.clock_in", {}, ctx
    )
    assert "You already have an open working day" in error.message
    assert Record.objects.filter(status="open").count() == 1


def test_a_user_without_a_staff_record_cannot_clock(make_user):
    ctx = ctx_for("hub_employee", actor=make_user("zoe"))
    for name in (
        "attendance.record.clock_in",
        "attendance.record.clock_out",
        "attendance.break.start",
        "attendance.break.end",
    ):
        refused("attendance.no_member_record", name, {}, ctx)


@pytest.mark.parametrize("status", [Member.Status.INACTIVE, Member.Status.ON_LEAVE])
def test_a_record_that_is_not_active_cannot_clock_in(person, clock, status):
    clock("2026-10-06T07:00")
    _, ctx = person(status=status)
    refused("attendance.member_not_active", "attendance.record.clock_in", {}, ctx)


def test_a_forgotten_day_is_flagged_when_the_person_clocks_in_again(person, clock):
    # ATTENDANCE-F05 without waiting for the worker: 12 h by default; the new day opens at once.
    clock("2026-10-05T07:00")
    ana, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    forgotten = Record.objects.get()
    clock("2026-10-06T07:00")
    run("attendance.record.clock_in", {}, ctx)
    forgotten.refresh_from_db()
    assert (forgotten.status, forgotten.clock_out_at) == ("needs_review", None)
    assert (
        Record.objects.filter(member=ana, status="open")
        .exclude(pk=forgotten.pk)
        .count()
        == 1
    )
    assert names()[-2:] == [events.RECORD_FLAGGED, events.CLOCKED_IN]


def test_an_open_day_younger_than_the_threshold_still_blocks(person, clock):
    AttendanceSettings.objects.create(auto_close_after_hours=10)
    clock("2026-10-06T07:00")
    _, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T16:59")
    refused("attendance.already_clocked_in", "attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T17:01")
    run("attendance.record.clock_in", {}, ctx)
    assert sorted(Record.objects.values_list("status", flat=True)) == [
        "needs_review",
        "open",
    ]

