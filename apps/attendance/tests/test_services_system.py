"""What the system runs: the review of forgotten days and closing the day of a terminated person."""

import datetime as dt

from apps.attendance import events
from apps.attendance.models import AttendanceSettings, Break, Correction, Record
from apps.attendance.schemas import ClosedOut, ReviewOut
from apps.staff.models import Member

from .conftest import HUB_DB, A, closed_day, names, outbox, run, utc

pytestmark = HUB_DB


# attendance.record.review_stale (ATTENDANCE-F05), as the scheduled task: the system


def test_the_review_flags_only_the_open_days_past_the_threshold(person, clock):
    from live.context import system_context

    clock("2026-10-06T20:00")
    ana, _ = person()
    bea, _ = person("Bea", "Ruiz")
    carl, _ = person("Carl", "Paz")
    old = Record.objects.create(
        member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6)
    )
    Record.objects.create(
        member=bea, clock_in_at=utc("2026-10-06T09:00"), work_date=dt.date(2026, 10, 6)
    )
    closed_day(carl, "2026-10-05T07:00", "2026-10-05T15:00")

    result = run("attendance.record.review_stale", {}, system_context(A))

    assert isinstance(result, ReviewOut)
    assert (result.flagged, result.record_ids) == (1, [old.id])
    assert sorted(Record.objects.values_list("status", flat=True)) == [
        "closed",
        "needs_review",
        "open",
    ]
    assert outbox() == [
        (events.RECORD_FLAGGED, {"id": str(old.id), "member_id": str(ana.id)})
    ]
    # Nothing new to flag: nothing said.
    assert run("attendance.record.review_stale", {}, system_context(A)).flagged == 0
    assert len(outbox()) == 1


def test_the_review_uses_the_businesss_hours(person, clock):
    from live.context import system_context

    AttendanceSettings.objects.create(auto_close_after_hours=1)
    clock("2026-10-06T08:30")
    ana, _ = person()
    Record.objects.create(
        member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6)
    )
    assert run("attendance.record.review_stale", {}, system_context(A)).flagged == 1


# attendance.record.close_for_terminated (ATTENDANCE-F13)


def test_a_termination_closes_the_day_and_its_break(person, clock):
    from live.context import system_context

    clock("2026-10-06T12:00")
    ana, _ = person()
    day = Record.objects.create(
        member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6)
    )
    pause = Break.objects.create(record=day, started_at=utc("2026-10-06T11:00"))
    Member.objects.filter(pk=ana.pk).update(status=Member.Status.TERMINATED)

    result = run(
        "attendance.record.close_for_terminated", {"id": str(ana.id)}, system_context(A)
    )

    assert isinstance(result, ClosedOut) and result.record.status == "closed"
    pause.refresh_from_db()
    assert pause.ended_at == utc("2026-10-06T12:00")
    trail = Correction.objects.get()
    assert (trail.is_system, trail.created_by_name) == (True, "")
    assert (trail.created_by, trail.reason, trail.old_status, trail.new_status) == (
        None,
        "Day closed when the person was terminated in Staff.",
        "open",
        "closed",
    )
    assert names() == [events.BREAK_ENDED, events.RECORD_CORRECTED]


def test_a_termination_without_an_open_day_changes_nothing(person, clock):
    from live.context import system_context

    clock("2026-10-06T12:00")
    ana, _ = person()
    closed_day(ana, "2026-10-05T07:00", "2026-10-05T15:00")
    assert (
        run(
            "attendance.record.close_for_terminated",
            {"id": str(ana.id)},
            system_context(A),
        ).record
        is None
    )
    assert outbox() == [] and Correction.objects.count() == 0




def test_the_reaction_closes_nothing_for_a_record_that_is_not_terminated(person, clock):
    # Only a termination closes a day; a stray call changes nothing.
    from live.context import system_context

    clock("2026-10-06T12:00")
    ana, _ = person()
    Record.objects.create(member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6))
    assert run("attendance.record.close_for_terminated", {"id": str(ana.id)}, system_context(A)).record is None
    assert Record.objects.get().status == "open"
    assert outbox() == [] and Correction.objects.count() == 0
