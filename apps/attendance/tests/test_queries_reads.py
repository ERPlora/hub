"""What the reads share, as they use it: the business's calendar day (a night shift counts on the day it started, and
the day is Madrid's, not UTC's) and the review hours of the saved settings."""

import datetime as dt

from apps.attendance.models import AttendanceSettings

from .conftest import HUB_DB, day, run

pytestmark = HUB_DB


def test_a_night_shift_counts_on_the_day_it_started(person, clock):
    # 22:00 → 06:00 in Madrid: one day, on the 5th; today (the 6th) has nothing running.
    clock("2026-10-06T03:00")  # 05:00 in Madrid
    ana, ctx = person()
    night = day(ana, "2026-10-05T20:00")
    result = run("attendance.record.current", {}, ctx)
    assert result.open.id == night.id and result.open.work_date == dt.date(2026, 10, 5)
    assert (result.today.worked_seconds, result.today.running) == (0, None)


def test_the_business_day_is_madrids_not_utcs(person, clock):
    # 23:30 UTC on the 5th is already 01:30 on the 6th in Madrid (old data.pg case).
    clock("2026-10-06T00:30")
    ana, ctx = person()
    day(ana, "2026-10-05T23:30")
    result = run("attendance.record.current", {}, ctx)
    assert result.open.work_date == dt.date(2026, 10, 6)
    assert (result.today.worked_seconds, result.today.running) == (3600, "work")


def test_a_forgotten_day_lists_as_needs_review_and_filters_so(person, clock):
    AttendanceSettings.objects.create(auto_close_after_hours=10)
    clock("2026-10-06T20:00")
    ana, ctx = person(role="hub_manager")
    stale = day(ana, "2026-10-06T07:00")
    bea, _ = person("Bea", "Ruiz")
    fresh = day(bea, "2026-10-06T12:00")
    rows = {row.id: row for row in run("attendance.record.list", {}, ctx).rows}
    assert (rows[stale.id].status, rows[stale.id].worked_seconds) == ("needs_review", None)
    assert (rows[fresh.id].status, rows[fresh.id].worked_seconds) == ("open", 8 * 3600)
    assert [r.id for r in run("attendance.record.list", {"status": "open"}, ctx).rows] == [fresh.id]
    assert [r.id for r in run("attendance.record.list", {"status": "needs_review"}, ctx).rows] == [stale.id]
