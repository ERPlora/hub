"""When a staff member can work: the schedule that governs each day minus their approved time off (STAFF-F16)."""

import datetime as dt
import uuid

import pytest
from live.errors import NotFound

from apps.staff.models import TimeOff
from apps.staff.queries.availability import member_availability
from apps.staff.schemas.availability import AvailabilityIn

from .conftest import HUB_DB, TERMINATED, ctx_for, make_member, make_schedule, make_time_off, run, t

pytestmark = HUB_DB

MONDAY = dt.date(2026, 10, 12)  # a Monday


def availability(member, start=MONDAY, end=None):
    data = AvailabilityIn(member_id=member.id, date_from=start, date_to=end or start)
    return member_availability(ctx_for("hub_employee"), data).days


def spans(intervals):
    return [
        (item.start.strftime("%H:%M"), item.end.strftime("%H:%M")) for item in intervals
    ]


def test_without_a_schedule_no_day_is_governed():
    [day] = availability(make_member())
    assert (day.date, day.schedule_id, day.shifts, day.time_off, day.available) == (
        MONDAY,
        None,
        [],
        [],
        [],
    )


def test_the_default_schedule_split_around_its_break():
    ana = make_member()
    usual = make_schedule(ana, {0: ("09:00", "18:00", "13:00", "14:00")})

    monday, tuesday = availability(ana, MONDAY, MONDAY + dt.timedelta(days=1))

    assert (monday.schedule_id, spans(monday.shifts), spans(monday.available)) == (
        usual.id,
        [("09:00", "13:00"), ("14:00", "18:00")],
        [("09:00", "13:00"), ("14:00", "18:00")],
    )
    # The schedule governs Tuesday too, as a day off: not «no schedule».
    assert (tuesday.date, tuesday.schedule_id, tuesday.shifts) == (
        MONDAY + dt.timedelta(days=1),
        usual.id,
        [],
    )


def test_a_break_at_an_edge_leaves_no_empty_piece():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00", "09:00", "10:00")})
    assert spans(availability(ana)[0].shifts) == [("10:00", "18:00")]


def test_a_specific_schedule_beats_the_default_within_its_dates():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00")})
    special = make_schedule(
        ana,
        {0: ("10:00", "12:00")},
        name="One day",
        is_default=False,
        effective_from=MONDAY,
        effective_until=MONDAY,
    )

    on, after = availability(ana, MONDAY, MONDAY + dt.timedelta(days=7))[0::7]

    assert (on.schedule_id, spans(on.shifts)) == (special.id, [("10:00", "12:00")])
    assert (after.date, spans(after.shifts)) == (
        MONDAY + dt.timedelta(days=7),
        [("09:00", "18:00")],
    )


def test_a_non_default_schedule_without_dates_beats_the_default_always():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00")})
    open_ended = make_schedule(
        ana, {0: ("08:00", "15:00")}, name="New", is_default=False
    )
    assert availability(ana)[0].schedule_id == open_ended.id


def test_between_specific_schedules_the_latest_start_then_the_newest_wins():
    ana = make_member()
    make_schedule(
        ana,
        {0: ("09:00", "10:00")},
        name="Autumn",
        is_default=False,
        effective_from=MONDAY - dt.timedelta(days=30),
    )
    late = make_schedule(
        ana,
        {0: ("09:00", "11:00")},
        name="Week",
        is_default=False,
        effective_from=MONDAY,
    )
    assert availability(ana)[0].schedule_id == late.id
    newer = make_schedule(
        ana,
        {0: ("09:00", "12:00")},
        name="Week bis",
        is_default=False,
        effective_from=MONDAY,
    )
    assert availability(ana)[0].schedule_id == newer.id


def test_an_inactive_or_out_of_date_schedule_never_governs():
    ana = make_member()
    usual = make_schedule(ana, {0: ("09:00", "18:00")})
    make_schedule(
        ana, {0: ("10:00", "11:00")}, name="Off", is_default=False, is_active=False
    )
    make_schedule(
        ana,
        {0: ("10:00", "11:00")},
        name="Past",
        is_default=False,
        effective_until=MONDAY - dt.timedelta(days=1),
    )
    make_schedule(
        ana,
        {0: ("10:00", "11:00")},
        name="Future",
        is_default=False,
        effective_from=MONDAY + dt.timedelta(days=1),
    )
    assert availability(ana)[0].schedule_id == usual.id


def test_an_approved_full_day_absence_leaves_nothing_available():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00")})
    make_time_off(
        ana,
        "2026-10-10",
        "2026-10-13",
        status=TimeOff.Status.APPROVED,
        leave_type="sick",
        reason="flu",
    )

    [day] = availability(ana)

    assert (spans(day.shifts), day.available) == ([("09:00", "18:00")], [])
    # The absence, without its type or its reason.
    assert [absence.model_dump() for absence in day.time_off] == [
        {"is_full_day": True, "start_time": None, "end_time": None}
    ]


def test_approved_part_day_absences_cut_the_shifts():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00", "13:00", "14:00")})
    make_time_off(
        ana, "2026-10-12", hours=("10:00", "11:00"), status=TimeOff.Status.APPROVED
    )
    make_time_off(
        ana, "2026-10-12", hours=("12:30", "15:00"), status=TimeOff.Status.APPROVED
    )

    [day] = availability(ana)

    assert spans(day.available) == [
        ("09:00", "10:00"),
        ("11:00", "12:30"),
        ("15:00", "18:00"),
    ]
    assert [(a.start_time, a.end_time) for a in day.time_off] == [
        (t("10:00"), t("11:00")),
        (t("12:30"), t("15:00")),
    ]


def test_an_absence_covering_a_whole_shift_removes_it():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00", "13:00", "14:00")})
    make_time_off(
        ana, "2026-10-12", hours=("08:00", "13:30"), status=TimeOff.Status.APPROVED
    )
    assert spans(availability(ana)[0].available) == [("14:00", "18:00")]


def test_part_day_absences_repeat_on_every_day_of_their_range():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "12:00"), 1: ("09:00", "12:00")})
    make_time_off(
        ana,
        "2026-10-12",
        "2026-10-13",
        hours=("09:00", "10:00"),
        status=TimeOff.Status.APPROVED,
    )
    assert [
        spans(day.available)
        for day in availability(ana, MONDAY, MONDAY + dt.timedelta(days=1))
    ] == [
        [("10:00", "12:00")],
        [("10:00", "12:00")],
    ]


def test_only_approved_absences_count():
    ana = make_member()
    make_schedule(ana, {0: ("09:00", "18:00")})
    for status in (
        TimeOff.Status.PENDING,
        TimeOff.Status.REJECTED,
        TimeOff.Status.CANCELLED,
    ):
        make_time_off(ana, "2026-10-12", status=status)
    [day] = availability(ana)
    assert (spans(day.available), day.time_off) == ([("09:00", "18:00")], [])


def test_one_row_per_day_of_the_range():
    days = availability(make_member(), MONDAY, MONDAY + dt.timedelta(days=730))
    assert (len(days), days[0].date, days[-1].date) == (
        731,
        MONDAY,
        MONDAY + dt.timedelta(days=730),
    )


def test_availability_of_a_terminated_or_missing_record_is_not_found():
    gone = make_member(status=TERMINATED)
    make_schedule(gone)
    with pytest.raises(NotFound):
        availability(gone)
    with pytest.raises(NotFound):
        run(
            "staff.availability.for_member",
            AvailabilityIn(member_id=uuid.uuid7(), date_from=MONDAY, date_to=MONDAY),
        )


def test_availability_of_a_member_named_by_name():
    ana = make_member("Ana", "López")
    make_schedule(ana, {0: ("09:00", "13:00")})
    data = AvailabilityIn(member="Ana", date_from=MONDAY, date_to=MONDAY)
    result = run("staff.availability.for_member", data)
    assert (result.member_id, spans(result.days[0].available)) == (ana.id, [("09:00", "13:00")])
