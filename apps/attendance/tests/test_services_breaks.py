"""The breaks of a working day and clocking out of it: attendance.break.start, .end and the clock-out."""

import datetime as dt

from apps.attendance import events
from apps.attendance.models import Break, Record

from .conftest import HUB_DB, outbox, refused, run, utc

pytestmark = HUB_DB


# attendance.record.clock_out and the breaks (ATTENDANCE-F01, F02)


def test_a_full_working_day_with_two_breaks(person, clock):
    clock("2026-10-06T07:00")
    ana, ctx = person()
    run("attendance.record.clock_in", {}, ctx)
    clock("2026-10-06T10:00")
    started = run("attendance.break.start", {}, ctx)
    assert started.break_started_at == utc("2026-10-06T10:00")
    clock("2026-10-06T10:15")
    ended = run("attendance.break.end", {}, ctx)
    assert ended.break_started_at is None and ended.break_seconds == 900
    clock("2026-10-06T13:00")
    run("attendance.break.start", {}, ctx)
    clock("2026-10-06T15:00")
    # Clocking out in the middle of a break ends it at that very moment.
    closed = run("attendance.record.clock_out", {}, ctx)
    assert (closed.status, closed.clock_out_at, closed.break_count) == (
        "closed",
        utc("2026-10-06T15:00"),
        2,
    )
    assert closed.break_seconds == 900 + 2 * 3600
    assert closed.worked_seconds == 8 * 3600 - closed.break_seconds
    assert list(
        Break.objects.order_by("started_at").values_list("ended_at", flat=True)
    ) == [
        utc("2026-10-06T10:15"),
        utc("2026-10-06T15:00"),
    ]
    day_id = str(closed.id)
    assert outbox() == [
        (events.CLOCKED_IN, {"id": day_id, "member_id": str(ana.id)}),
        (
            events.BREAK_STARTED,
            {
                "id": str(Break.objects.order_by("started_at")[0].id),
                "record_id": day_id,
                "member_id": str(ana.id),
            },
        ),
        (
            events.BREAK_ENDED,
            {
                "id": str(Break.objects.order_by("started_at")[0].id),
                "record_id": day_id,
                "member_id": str(ana.id),
            },
        ),
        (
            events.BREAK_STARTED,
            {
                "id": str(Break.objects.order_by("started_at")[1].id),
                "record_id": day_id,
                "member_id": str(ana.id),
            },
        ),
        (
            events.BREAK_ENDED,
            {
                "id": str(Break.objects.order_by("started_at")[1].id),
                "record_id": day_id,
                "member_id": str(ana.id),
            },
        ),
        (events.CLOCKED_OUT, {"id": day_id, "member_id": str(ana.id)}),
    ]


def test_the_guards_answer_their_codes(person, clock):
    clock("2026-10-06T07:00")
    _, ctx = person()
    refused("attendance.no_break_running", "attendance.break.end", {}, ctx)
    refused("attendance.not_clocked_in", "attendance.break.start", {}, ctx)
    refused("attendance.not_clocked_in", "attendance.record.clock_out", {}, ctx)
    run("attendance.record.clock_in", {}, ctx)
    refused("attendance.no_break_running", "attendance.break.end", {}, ctx)
    clock("2026-10-06T08:00")
    run("attendance.break.start", {}, ctx)
    refused("attendance.break_running", "attendance.break.start", {}, ctx)


def test_a_day_waiting_for_review_cannot_be_clocked_out(person, clock):
    clock("2026-10-06T07:00")
    ana, ctx = person()
    Record.objects.create(
        member=ana,
        clock_in_at=utc("2026-10-04T07:00"),
        work_date=dt.date(2026, 10, 4),
        status="needs_review",
    )
    refused("attendance.not_clocked_in", "attendance.record.clock_out", {}, ctx)
