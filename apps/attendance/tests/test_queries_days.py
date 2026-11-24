"""How a working day's durations count as of a moment: its breaks out, an open day until now, a day waiting for review
without worked time; and when an open day is a forgotten one."""

from apps.attendance import queries
from apps.attendance.models import Record

from .conftest import HUB_DB, NOW, day, run, utc

pytestmark = HUB_DB


# Durations


def test_a_closed_day_counts_its_breaks_out(person, clock):
    clock(NOW)
    ana, ctx = person()
    day(
        ana,
        "2026-10-05T07:02:41",
        "2026-10-05T15:05:03",
        breaks=[("2026-10-05T11:00", "2026-10-05T11:30")],
    )
    row = run("attendance.record.list", {}, ctx).rows[0]
    assert (row.break_count, row.break_seconds) == (1, 1800)
    assert row.worked_seconds == (8 * 3600 + 2 * 60 + 22) - 1800
    assert row.break_started_at is None


def test_an_open_day_counts_until_now_and_its_running_break_too(person, clock):
    clock(NOW)
    ana, ctx = person()
    day(ana, "2026-10-06T08:00", breaks=[("2026-10-06T10:00", None)])
    row = run("attendance.record.list", {}, ctx).rows[0]
    assert (row.break_seconds, row.worked_seconds) == (30 * 60, 2 * 3600)
    assert row.as_of == utc(NOW)


def test_a_day_waiting_for_review_has_no_worked_time(person, clock):
    # «Until now» would count the days nobody worked: it stays empty until a manager corrects it.
    clock(NOW)
    ana, ctx = person()
    day(ana, "2026-10-04T08:00", status="needs_review")
    row = run("attendance.record.list", {}, ctx).rows[0]
    assert (row.status, row.worked_seconds) == ("needs_review", None)


# A forgotten day (open longer than the settings' hours) reads as waiting for review, whether or not
# the worker's review has run yet (every quarter of an hour): it never counts «until now».


def test_is_stale_is_an_open_day_past_the_hours():
    start = utc("2026-10-05T07:00")
    open_day = Record(clock_in_at=start, status="open")
    assert queries.days.is_stale(open_day, 12, utc("2026-10-05T19:01")) is True
    assert queries.days.is_stale(open_day, 12, utc("2026-10-05T19:00")) is False
    assert queries.days.is_stale(open_day, 24, utc("2026-10-05T19:01")) is False
    for status in ("closed", "needs_review"):
        assert queries.days.is_stale(Record(clock_in_at=start, status=status), 12, utc("2026-10-07T07:00")) is False


def test_a_running_break_of_a_day_waiting_for_review_does_not_grow(person, clock):
    clock("2026-10-08T07:00")
    ana, ctx = person()
    day(
        ana,
        "2026-10-05T07:00",
        status="needs_review",
        breaks=[("2026-10-05T09:00", "2026-10-05T09:30"), ("2026-10-05T12:00", None)],
    )
    row = run("attendance.record.list", {}, ctx).rows[0]
    assert (row.break_seconds, row.worked_seconds) == (1800, None)
