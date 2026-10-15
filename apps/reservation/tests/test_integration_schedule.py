"""Reservations with the real Schedules app: a reservation starts with the business open (its usual week
once confirmed, its special days and its temporary changes), read on behalf of whoever books even without
any right in Schedules. Nothing is mocked."""

import datetime as dt

import pytest
from live.context import system_context
from live.errors import Conflict

from .conftest import (
    A,
    THURSDAY,
    book,
    ctx_for,
    make_slot,
    open_week,
    run,
    set_week_hours,
)

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"


@pytest.fixture(autouse=True)
def week(db):
    open_week()


def refused(**data) -> str:
    with pytest.raises(Conflict) as caught:
        book(**data)
    return caught.value.code


def test_a_confirmed_week_turns_away_a_time_the_business_is_closed():
    set_week_hours([("13:00", "16:00")])
    assert refused(time="21:00") == "reservation.outside_schedule"
    assert book(time="14:00").status == "pending"


def test_the_host_books_inside_the_hours_without_any_right_in_schedules():
    set_week_hours([("12:00", "23:59")])
    host = ctx_for(
        EMPLOYEE,
        permissions={"reservation.add_reservation", "customer.view", "customer.manage"},
    )
    assert book(ctx=host).status == "pending"


def test_a_closed_special_day_turns_away_even_without_a_confirmed_week():
    run(
        "schedule.special_day.create",
        {"date": "2026-10-15", "name": "Local holiday", "is_closed": True},
        system_context(A),
    )
    assert refused() == "reservation.outside_schedule"


def test_a_temporary_change_open_all_day_lets_a_late_dinner_in():
    set_week_hours([("13:00", "16:00")])
    run(
        "schedule.override.create",
        {
            "start_date": "2026-10-15",
            "end_date": "2026-10-15",
            "reason": "Festival",
            "is_closed": False,
            "intervals": [{"open_time": "00:00", "close_time": "00:00"}],
        },
        system_context(A),
    )
    assert book(time="23:00").status == "pending"


def test_the_eves_hours_past_midnight_count():
    set_week_hours([("20:00", "02:00")])
    make_slot(THURSDAY + 1, "00:00", "03:00")
    assert book(date="2026-10-16", time="01:00").time == dt.time(1, 0)
    assert refused(date="2026-10-16", time="02:30") == "reservation.outside_schedule"


def test_the_day_shows_the_business_hours_and_the_slots_outside_them():
    set_week_hours([("13:00", "16:00")])
    day = run("reservation.availability.day", {"date": "2026-10-15"}, ctx_for(EMPLOYEE))
    assert day.hours_restricted is True
    assert [(f"{slot.start_time:%H:%M}", slot.in_hours) for slot in day.slots] == [
        ("13:00", True),
        ("20:00", False),
    ]


def test_a_conversion_from_the_waitlist_also_needs_the_business_open():
    set_week_hours([("13:00", "16:00")])
    entry = run(
        "reservation.waitlist.create",
        {
            "guest_name": "Luis",
            "date": "2026-10-15",
            "preferred_time": "21:00",
            "party_size": 2,
        },
    )
    with pytest.raises(Conflict) as caught:
        run("reservation.waitlist.convert", {"id": str(entry.id)})
    assert caught.value.code == "reservation.outside_schedule"
