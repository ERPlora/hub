"""Appointments with the real Schedules app: the business's week, special days and temporary changes are
Schedules', written by its own operations; the agenda reads them through ``schedule.hours.for_range``.
"""

import datetime as dt

import pytest
from live.errors import Conflict

from .conftest import MONDAY, make_customer, make_member, make_service, make_tax, run, wall

pytestmark = pytest.mark.django_db


@pytest.fixture
def cast(db):
    make_service("Haircut", duration=30, tax=make_tax())
    make_customer("Lucía Pérez")
    make_member("Ana", "López")


def book(day: dt.date, start: str):
    return run(
        "appointment.appointment.create",
        {"customer": "Lucía Pérez", "services": [{"service": "Haircut"}], "staff": "Ana", "start": wall(day, start)},
    )


def code_of(call) -> str:
    with pytest.raises(Conflict) as refused:
        call()
    return refused.value.code


def test_the_seeded_week_of_schedules_opens_monday_to_friday_nine_to_six(cast):
    assert book(MONDAY, "09:00").status == "confirmed"
    assert book(MONDAY, "17:30").status == "confirmed"  # ends at closing
    assert code_of(lambda: book(MONDAY, "17:45")) == "appointment.outside_schedule"
    assert code_of(lambda: book(MONDAY + dt.timedelta(days=5), "10:00")) == "appointment.outside_schedule"


def test_a_special_day_closes_and_a_day_set_in_schedules_moves_the_hours(cast):
    run("schedule.special_day.create", {"date": MONDAY.isoformat(), "name": "Local holiday"})
    assert code_of(lambda: book(MONDAY, "10:00")) == "appointment.outside_schedule"
    tuesday = MONDAY + dt.timedelta(days=1)
    run("schedule.week.set_day", {"weekday": 1, "intervals": [{"open_time": "16:00", "close_time": "22:00"}]})
    assert code_of(lambda: book(tuesday, "10:00")) == "appointment.outside_schedule"
    assert book(tuesday, "21:30").status == "confirmed"


def test_an_overnight_span_opens_the_small_hours_of_the_next_day(cast):
    run("schedule.week.set_day", {"weekday": 4, "intervals": [{"open_time": "20:00", "close_time": "02:00"}]})
    run("schedule.week.set_day", {"weekday": 5, "is_closed": True})
    friday = MONDAY + dt.timedelta(days=4)
    assert book(friday + dt.timedelta(days=1), "01:00").status == "confirmed"
    slots = run("appointment.settings.update", {"calendar_start_hour": 0, "calendar_end_hour": 24})
    assert slots.calendar_end_hour == 24
    out = run("appointment.availability.slots", {"date": friday + dt.timedelta(days=1), "duration_minutes": 30, "staff": "Ana"})
    assert [f"{slot.start:%H:%M}" for slot in out.slots][:2] == ["00:00", "00:15"]
