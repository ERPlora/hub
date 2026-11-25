"""Correcting a working day: attendance.record.correct, its trail and its guards."""

import datetime as dt

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.attendance import events
from apps.attendance.models import Break, Correction, Record
from apps.staff.models import Member

from .conftest import HUB_DB, closed_day, ctx_for, outbox, run, utc

pytestmark = HUB_DB


# attendance.record.correct (ATTENDANCE-F08, F09)


def correct(record, start, end, reason="Forgot to clock out", ctx=None):
    data = {
        "record_id": str(record.id),
        "clock_in_at": f"{start}:00Z",
        "clock_out_at": f"{end}:00Z" if end else None,
        "reason": reason,
    }
    return run("attendance.record.correct", data, ctx)


def test_a_correction_rewrites_the_day_and_leaves_its_trail(person, clock, make_user):
    clock("2026-10-07T09:00")
    ana, _ = person()
    boss = make_user("boss", role="hub_manager")
    day = closed_day(ana, "2026-10-06T07:00", "2026-10-06T07:05")
    result = correct(
        day,
        "2026-10-05T06:00",
        "2026-10-05T14:30",
        ctx=ctx_for("hub_manager", actor=boss),
    )
    day.refresh_from_db()
    assert (day.clock_in_at, day.clock_out_at, day.status, day.updated_by) == (
        utc("2026-10-05T06:00"),
        utc("2026-10-05T14:30"),
        "closed",
        boss.person,
    )
    # The business day follows the new clock-in.
    assert day.work_date == dt.date(2026, 10, 5) and result.work_date == day.work_date
    trail = Correction.objects.get()
    assert (trail.old_clock_in_at, trail.old_clock_out_at, trail.old_status) == (
        utc("2026-10-06T07:00"),
        utc("2026-10-06T07:05"),
        "closed",
    )
    assert (trail.new_clock_in_at, trail.new_clock_out_at, trail.new_status) == (
        utc("2026-10-05T06:00"),
        utc("2026-10-05T14:30"),
        "closed",
    )
    assert (trail.reason, trail.created_by) == ("Forgot to clock out", boss.person)
    # Who corrected is copied: a deleted user never turns into «System».
    assert (trail.is_system, trail.created_by_name) == (False, "boss")
    assert outbox() == [
        (
            events.RECORD_CORRECTED,
            {
                "id": str(day.id),
                "member_id": str(ana.id),
                "correction_id": str(trail.id),
            },
        )
    ]


def test_correcting_a_day_that_does_not_exist(clock):
    clock("2026-10-07T09:00")
    ghost = Record(id=None)
    with pytest.raises(NotFound):
        run(
            "attendance.record.correct",
            {
                "record_id": "0199c8a0-0000-7000-8000-000000000000",
                "clock_in_at": "2026-10-06T07:00:00Z",
                "reason": "Ghost",
            },
        )
    assert ghost.pk is None and Correction.objects.count() == 0


def test_an_employee_cannot_correct(person, clock):
    clock("2026-10-07T09:00")
    ana, ctx = person()
    day = closed_day(ana, "2026-10-06T07:00", "2026-10-06T15:00")
    with pytest.raises(PermissionDenied):
        correct(day, "2026-10-06T06:00", "2026-10-06T15:00", ctx=ctx)


def test_a_correction_cannot_be_in_the_future(person, clock):
    clock("2026-10-07T09:00")
    ana, _ = person()
    day = closed_day(ana, "2026-10-06T07:00", "2026-10-06T15:00")
    for start, end, field in (
        ("2026-10-07T09:30", None, "clock_in_at"),
        ("2026-10-07T07:00", "2026-10-07T10:00", "clock_out_at"),
    ):
        with pytest.raises(InvalidPayload) as caught:
            correct(day, start, end)
        assert list(caught.value.fields) == [field]
    assert Correction.objects.count() == 0


def test_without_a_clock_out_the_day_is_open_again(person, clock):
    clock("2026-10-07T09:00")
    ana, _ = person()
    day = closed_day(ana, "2026-10-07T07:00", "2026-10-07T07:01")
    correct(day, "2026-10-07T07:00", None)
    day.refresh_from_db()
    assert (day.status, day.clock_out_at) == ("open", None)


def test_reopening_a_day_while_another_is_open_is_refused(person, clock):
    clock("2026-10-07T09:00")
    ana, ctx = person()
    day = closed_day(ana, "2026-10-06T07:00", "2026-10-06T15:00")
    run("attendance.record.clock_in", {}, ctx)
    OutboxEvent.objects.all().delete()
    with pytest.raises(Conflict) as caught:
        correct(day, "2026-10-06T07:00", None)
    assert caught.value.code == "attendance.second_open_day"
    assert Correction.objects.count() == 0 and outbox() == []


def test_a_day_waiting_for_review_is_closed_with_a_correction_and_its_break_too(
    person, clock
):
    clock("2026-10-07T09:00")
    ana, _ = person()
    day = Record.objects.create(
        member=ana,
        clock_in_at=utc("2026-10-06T07:00"),
        work_date=dt.date(2026, 10, 6),
        status="needs_review",
    )
    running = Break.objects.create(record=day, started_at=utc("2026-10-06T13:00"))
    correct(day, "2026-10-06T07:00", "2026-10-06T15:00")
    day.refresh_from_db()
    running.refresh_from_db()
    assert (day.status, running.ended_at) == ("closed", utc("2026-10-06T15:00"))
    # A break left running that began after the new clock-out ends at its own start.
    late = Record.objects.create(
        member=ana,
        clock_in_at=utc("2026-10-05T07:00"),
        work_date=dt.date(2026, 10, 5),
        status="needs_review",
    )
    after = Break.objects.create(record=late, started_at=utc("2026-10-05T16:00"))
    correct(late, "2026-10-05T07:00", "2026-10-05T15:00")
    after.refresh_from_db()
    assert after.ended_at == utc("2026-10-05T16:00")


class TestOverlap:
    """A correction never puts two days of the same person over each other."""

    @pytest.fixture
    def days(self, person, clock):
        clock("2026-10-06T13:00")
        ines, _ = person("Ines", "Mar")
        joan, _ = person("Joan", "Sol")
        first = closed_day(ines, "2026-10-06T08:00", "2026-10-06T09:00")
        second = closed_day(ines, "2026-10-06T10:00", "2026-10-06T11:00")
        closed_day(joan, "2026-10-06T08:30", "2026-10-06T09:30")
        return ines, first, second

    def refused_overlap(self, record, start, end):
        record.refresh_from_db()
        before = (record.clock_in_at, record.clock_out_at)
        trail = Correction.objects.filter(record=record).count()
        with pytest.raises(Conflict) as caught:
            correct(record, start, end)
        assert caught.value.code == "attendance.overlap"
        record.refresh_from_db()
        assert (record.clock_in_at, record.clock_out_at) == before
        assert Correction.objects.filter(record=record).count() == trail

    def test_moving_a_day_over_another_of_the_same_person(self, days):
        _, _, second = days
        self.refused_overlap(second, "2026-10-06T08:30", "2026-10-06T10:30")
        self.refused_overlap(second, "2026-10-06T07:00", "2026-10-06T12:00")

    def test_touching_is_not_overlapping_and_another_persons_day_never_blocks(
        self, days
    ):
        _, _, second = days
        correct(second, "2026-10-06T09:00", "2026-10-06T11:00")
        assert Correction.objects.filter(record=second).count() == 1

    def test_an_open_day_runs_until_now(self, days, clock):
        ines, _, second = days
        Record.objects.create(
            member=ines,
            clock_in_at=utc("2026-10-06T12:00"),
            work_date=dt.date(2026, 10, 6),
        )
        self.refused_overlap(second, "2026-10-06T11:30", "2026-10-06T12:30")
        correct(second, "2026-10-06T11:00", "2026-10-06T11:59")

    def test_reopening_runs_until_now_over_a_later_day(self, days):
        _, first, _ = days
        Record.objects.filter(member=first.member, status="open").delete()
        self.refused_overlap(first, "2026-10-06T08:00", None)

    def test_a_forgotten_day_is_only_its_clock_in(self, days, person):
        kai, _ = person("Kai", "Lin")
        Record.objects.create(
            member=kai,
            clock_in_at=utc("2026-10-06T08:00"),
            work_date=dt.date(2026, 10, 6),
            status="needs_review",
        )
        later = closed_day(kai, "2026-10-06T10:00", "2026-10-06T11:00")
        correct(later, "2026-10-06T09:00", "2026-10-06T11:00")
        self.refused_overlap(later, "2026-10-06T07:00", "2026-10-06T11:00")



def test_the_open_day_of_a_terminated_record_is_closed_by_a_correction(person, clock):
    # The person no longer clocks (their record is terminated): a manager closes the day.
    clock("2026-10-06T18:00")
    ana, _ = person()
    open_day = Record.objects.create(member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6))
    Member.objects.filter(pk=ana.pk).update(status=Member.Status.TERMINATED)
    corrected = correct(open_day, "2026-10-06T07:00", "2026-10-06T15:00", reason="Closed after leaving")
    assert corrected.status == "closed"
