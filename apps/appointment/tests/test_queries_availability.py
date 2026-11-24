"""The free times of a day, and whether a time can be booked and why not."""

import datetime as dt

import pytest

from apps.appointment.queries.availability import availability_slots
from apps.appointment.schemas import SlotsIn
from apps.staff.models import Member

from .conftest import (
    HUB_DB,
    MONDAY,
    as_ctx,
    assign,
    at,
    ctx_for,
    employee_linked_to,
    make_appointment,
    make_block,
    make_day,
    make_settings,
    make_shift,
    make_time_off,
    pin_clock,
    run,
    wall,
)

pytestmark = HUB_DB


def test_with_nobody_who_takes_bookings_the_free_times_are_the_businesss_own(salon):
    Member.objects.update(is_bookable=False)
    make_settings(slot_interval=60)
    make_day(0, ("09:00", "11:00"))
    out = availability_slots(ctx_for(), SlotsIn(date=MONDAY, duration_minutes=60))
    assert (starts(out), out.duration_minutes) == (["09:00", "10:00"], 60)
    assert all(slot.staff_ids == [] for slot in out.slots)


def starts(out) -> list[str]:
    return [f"{slot.start:%H:%M}" for slot in out.slots]


def test_free_times_cross_the_business_hours_the_shift_the_blocks_and_the_appointments(
    salon,
):
    make_settings(slot_interval=30, allow_overlapping=False)
    make_day(0, ("09:00", "13:00"))
    make_shift(salon.ana, (0, "10:00", "14:00"))
    make_block(at(MONDAY, "11:00"), at(MONDAY, "11:30"), member=salon.ana)
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"))
    out = run(
        "appointment.availability.slots",
        {"date": MONDAY, "services": ["Haircut"], "staff": "Ana"},
    )
    assert starts(out) == ["10:00", "10:30", "11:30", "12:30"]
    assert (out.duration_minutes, out.timezone) == (30, "Europe/Madrid")
    assert all(slot.staff_ids == [salon.ana.id] for slot in out.slots)


def test_free_times_take_the_professionals_own_length_and_ignore_the_appointment_being_moved(
    salon,
):
    make_settings(slot_interval=30, allow_overlapping=False)
    make_day(0, ("09:00", "11:00"))
    assign(salon.cut, salon.ana, duration=60)
    moving = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), duration=60
    )
    query = {"date": MONDAY, "services": ["Haircut"], "staff": "Ana"}
    assert starts(run("appointment.availability.slots", query)) == ["10:00"]
    assert starts(
        run("appointment.availability.slots", {**query, "exclude_id": str(moving.id)})
    ) == [
        "09:00",
        "09:30",
        "10:00",
    ]


def test_free_times_without_a_professional_say_who_is_free_among_those_who_do_the_service(
    salon,
):
    make_settings(slot_interval=60, allow_overlapping=False)
    make_day(0, ("09:00", "11:00"))
    assign(salon.colour, salon.ana)
    assign(salon.colour, salon.bea)
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"))
    out = run(
        "appointment.availability.slots",
        {"date": MONDAY, "services": ["Colour"]},
    )
    assert [(f"{s.start:%H:%M}", sorted(s.staff_ids)) for s in out.slots] == [
        ("09:00", [salon.bea.id]),
        ("10:00", sorted([salon.ana.id, salon.bea.id])),
    ]


def test_a_service_nobody_is_assigned_to_is_offered_with_the_whole_bookable_team(salon):
    make_settings(slot_interval=60)
    make_day(0, ("09:00", "10:00"))
    salon.bea.is_bookable = False
    salon.bea.save()
    out = run(
        "appointment.availability.slots",
        {"date": MONDAY, "services": ["Haircut"]},
    )
    assert [s.staff_ids for s in out.slots] == [[salon.ana.id]]


@pytest.mark.parametrize(
    ("today", "clock", "asked", "first"),
    [
        pytest.param(dt.date(2026, 11, 9), "10:00", dt.date(2026, 11, 10), "10:00", id="ordinary-day"),
        # hub#688: from here tomorrow's midnight is 24 h 28 min away, so the whole day keeps the notice.
        pytest.param(dt.date(2026, 10, 25), "00:32", dt.date(2026, 10, 26), "00:00", id="25h-day-before-1am"),
        pytest.param(dt.date(2026, 10, 25), "01:30", dt.date(2026, 10, 26), "01:00", id="25h-day-after-1am"),
        pytest.param(dt.date(2026, 10, 24), "10:00", dt.date(2026, 10, 25), "09:00", id="eve-of-the-25h-day"),
        pytest.param(dt.date(2027, 3, 28), "00:32", dt.date(2027, 3, 29), "02:00", id="23h-day"),
        pytest.param(dt.date(2027, 3, 27), "10:00", dt.date(2027, 3, 28), "11:00", id="eve-of-the-23h-day"),
    ],
)
def test_the_customer_is_offered_only_what_keeps_the_notice(salon, monkeypatch, today, clock, asked, first):
    """24 hours of notice are 24 real hours: the days the clock changes they end at another wall time."""
    instant = at(today, clock).astimezone(dt.UTC)
    pin_clock(monkeypatch, instant)
    make_settings(
        min_booking_notice=24 * 60,
        slot_interval=60,
        calendar_start_hour=0,
        calendar_end_hour=24,
    )
    make_day(asked.weekday(), ("00:00", "00:00"))
    desk = run(
        "appointment.availability.slots", {"date": asked, "duration_minutes": 60}
    ).slots
    customer = run(
        "appointment.availability.slots",
        {"date": asked, "duration_minutes": 60, "for_customer": True},
    ).slots
    hours = [f"{slot.start:%H:%M}" for slot in desk]
    assert hours[0] == "00:00"  # The front desk sees the whole day: the notice only marks its hours.
    keeps = hours.index(first)
    assert [f"{slot.start:%H:%M}" for slot in customer] == hours[keeps:]
    assert all(not slot.within_notice for slot in customer)
    assert [f"{slot.start:%H:%M}" for slot in desk if slot.within_notice] == hours[:keeps]
    # ``instant`` is in UTC, so these subtractions count real time, not the wall clock's.
    notice = dt.timedelta(hours=24)
    assert all(slot.start - instant >= notice for slot in customer)
    assert all(slot.start - instant < notice for slot in desk if slot.within_notice)


@pytest.mark.parametrize(
    ("day", "start", "minutes", "end"),
    [
        pytest.param(dt.date(2026, 10, 25), "02:30", 60, "2026-10-25T02:30:00+01:00", id="25h-day"),
        pytest.param(dt.date(2027, 3, 28), "01:30", 60, "2027-03-28T03:30:00+02:00", id="23h-day"),
    ],
)
def test_a_free_time_says_its_real_end_on_the_business_clock(salon, monkeypatch, day, start, minutes, end):
    pin_clock(monkeypatch, at(day, "00:01"))
    make_settings(slot_interval=30, calendar_start_hour=0, calendar_end_hour=24)
    make_day(day.weekday(), ("00:00", "00:00"))
    slots = run("appointment.availability.slots", {"date": day, "duration_minutes": minutes}).slots
    found = {f"{slot.start:%H:%M}": slot for slot in slots}
    assert found[start].end.isoformat() == end


@pytest.mark.parametrize(
    ("start", "code"),
    [
        ("10:00", None),
        ("08:30", "outside_schedule"),
        ("13:00", "outside_staff_hours"),
        ("11:00", "blocked"),
        ("12:00", "overlap"),
    ],
)
def test_a_time_is_answered_with_the_reason_it_cannot_be_booked(salon, start, code):
    make_settings(allow_overlapping=False)
    make_day(0, ("09:00", "14:00"))
    make_shift(salon.ana, (0, "09:00", "13:00"))
    make_block(at(MONDAY, "11:00"), at(MONDAY, "11:30"))
    make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), number="APT-OVER"
    )
    out = run(
        "appointment.availability.check",
        {
            "start": wall(MONDAY, start),
            "services": ["Haircut"],
            "staff": "Ana",
        },
    )
    assert (out.available, out.code) == (code is None, code)
    if code == "overlap":
        assert [c.number for c in out.conflicts] == ["APT-OVER"]
        assert "already has an appointment" in out.message
    if code is None:
        assert out.message == ""


def test_an_employee_hears_a_colleagues_time_is_taken_but_not_by_whom(salon, make_user):
    make_settings(allow_overlapping=False)
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), number="APT-ANA")
    make_appointment(salon.lucia, salon.bea, [salon.cut], at(MONDAY, "12:00"), number="APT-BEA")
    ctx = employee_linked_to(salon.bea, make_user)
    asked = {"start": wall(MONDAY, "12:00"), "duration_minutes": 30}
    colleague = as_ctx(ctx, "appointment.availability.check", {**asked, "staff": "Ana"})
    assert (colleague.code, colleague.conflicts) == ("overlap", [])
    own = as_ctx(ctx, "appointment.availability.check", {**asked, "staff": "Bea"})
    assert [c.number for c in own.conflicts] == ["APT-BEA"]
    owner = run("appointment.availability.check", {**asked, "staff": "Ana"})
    assert [c.number for c in owner.conflicts] == ["APT-ANA"]


def test_approved_time_off_without_a_schedule_refuses_and_the_business_alone_ignores_people(
    salon,
):
    make_day(0, ("09:00", "14:00"))
    make_time_off(salon.ana, MONDAY)
    asked = {"start": wall(MONDAY, "10:00"), "duration_minutes": 30}
    assert (
        run("appointment.availability.check", {**asked, "staff": "Ana"}).code
        == "outside_staff_hours"
    )
    assert run("appointment.availability.check", asked).available is True


@pytest.mark.parametrize(
    ("day", "taken", "start", "minutes", "code"),
    [
        # 00:30 + 3 real hours ends at 04:30 on the wall: 04:00 is taken (the wall clock's sum ended at 03:30).
        pytest.param(dt.date(2027, 3, 28), "04:00", "00:30", 180, "overlap", id="23h-day-taken"),
        # 01:00 + 2.5 real hours ends at 02:30 the second time: 03:00 is free (the wall clock's sum ended at 03:30).
        pytest.param(dt.date(2026, 10, 25), "03:00", "01:00", 150, None, id="25h-day-free"),
    ],
)
def test_a_times_verdict_counts_its_real_end_the_nights_the_clock_changes(salon, monkeypatch, day, taken, start, minutes, code):
    pin_clock(monkeypatch, at(day, "00:01"))
    make_settings(allow_overlapping=False)
    make_day(day.weekday(), ("00:00", "00:00"))
    make_appointment(salon.lucia, salon.ana, [salon.cut], at(day, taken), number="APT-THERE")
    out = run(
        "appointment.availability.check",
        {"start": wall(day, start), "duration_minutes": minutes, "staff": "Ana"},
    )
    assert (out.available, out.code) == (code is None, code)
