"""Blocked times, for the business or one professional (APPOINTMENT-F16)."""

import datetime as dt

import pytest
from live.errors import PermissionDenied

from apps.appointment.models.blocked_times import BlockedTime

from .conftest import HUB_DB, MONDAY, at, run, wall
from .write_checks import book, events, refused

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


def test_a_block_is_created_for_the_business_or_one_professional_and_removed(salon):
    block = run(
        "appointment.blocked_time.create",
        {
            "title": "Training",
            "start": wall(MONDAY, "12:00"),
            "end": wall(MONDAY, "13:00"),
            "staff": "Ana",
        },
    )
    assert (block.staff_id, block.start) == (salon.ana.id, at(MONDAY, "12:00"))
    refused("appointment.blocked", lambda: book(salon, "12:30"))
    holiday = run(
        "appointment.blocked_time.create",
        {
            "title": "Holiday",
            "block_type": "holiday",
            "start": wall(MONDAY, "15:00"),
            "end": wall(MONDAY, "15:00"),
            "all_day": True,
        },
    )
    assert (holiday.start, holiday.end) == (
        at(MONDAY, "00:00"),
        at(MONDAY + dt.timedelta(days=1), "00:00"),
    )
    assert len(events("appointment.blocked_time.created")) == 2
    run("appointment.blocked_time.delete", {"id": str(block.id)})
    assert not BlockedTime.objects.filter(pk=block.id).exists()
    assert len(events("appointment.blocked_time.deleted")) == 1


def test_an_employee_does_not_block_time():
    with pytest.raises(PermissionDenied):
        run(
            "appointment.blocked_time.create",
            {
                "title": "x",
                "start": wall(MONDAY, "12:00"),
                "end": wall(MONDAY, "13:00"),
            },
            role="hub_employee",
        )
