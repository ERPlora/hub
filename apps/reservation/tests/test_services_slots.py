"""Writes of the book's time slots (``reservation.time_slot.*``)."""

import pytest
from live.errors import NotFound, PermissionDenied

from apps.reservation.models import TimeSlot

from .conftest import EMPLOYEE, HUB_DB, MANAGER, ctx_for, events, refusal, run

pytestmark = HUB_DB


def test_a_manager_creates_and_removes_slots_that_do_not_overlap():
    manager = ctx_for(MANAGER)
    lunch = run(
        "reservation.time_slot.create",
        {"day_of_week": 3, "start_time": "13:00", "end_time": "16:00"},
        manager,
    )
    assert (lunch.max_reservations, lunch.max_covers) == (10, None)
    error = refusal(
        lambda: run(
            "reservation.time_slot.create",
            {"day_of_week": 3, "start_time": "15:30", "end_time": "17:00"},
            manager,
        )
    )
    assert (error.code, error.message) == (
        "reservation.slot_overlaps",
        "That slot overlaps another one of the same day (13:00–16:00).",
    )
    assert (
        run(
            "reservation.time_slot.create",
            {
                "day_of_week": 3,
                "start_time": "16:00",
                "end_time": "18:00",
                "max_covers": 30,
            },
            manager,
        ).max_covers
        == 30
    )
    run(
        "reservation.time_slot.delete",
        {"day_of_week": 3, "start_time": "13:00"},
        manager,
    )
    assert TimeSlot.objects.get(pk=lunch.id).is_deleted is True
    assert (
        run(
            "reservation.time_slot.create",
            {"day_of_week": 3, "start_time": "13:00", "end_time": "16:00"},
            manager,
        ).id
        != lunch.id
    )
    assert events() == [
        "reservation.time_slot.created",
        "reservation.time_slot.created",
        "reservation.time_slot.deleted",
        "reservation.time_slot.created",
    ]
    with pytest.raises(PermissionDenied):
        run(
            "reservation.time_slot.create",
            {"day_of_week": 4, "start_time": "13:00", "end_time": "16:00"},
            ctx_for(EMPLOYEE),
        )


def test_a_missing_slot_is_not_found():
    with pytest.raises(NotFound) as caught:
        run("reservation.time_slot.delete", {"day_of_week": 3, "start_time": "13:00"})
    assert caught.value.code == "reservation.slot_not_found"
