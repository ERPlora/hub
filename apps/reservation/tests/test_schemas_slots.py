"""The inputs of the time slots: a slot ends after it starts, on a weekday, and is named by its id or by its
day and start."""

import datetime as dt

from apps.reservation.schemas.slots import TimeSlotIn, TimeSlotRefIn

from .conftest import errors


def test_a_slot_ends_after_it_starts_on_a_weekday():
    assert "end_time" in errors(
        TimeSlotIn, {"day_of_week": 3, "start_time": "21:00", "end_time": "20:00"}
    )
    assert "day_of_week" in errors(
        TimeSlotIn, {"day_of_week": 7, "start_time": "20:00", "end_time": "23:00"}
    )
    assert "max_covers" in errors(
        TimeSlotIn,
        {"day_of_week": 3, "start_time": "20:00", "end_time": "23:00", "max_covers": 0},
    )
    slot = TimeSlotIn.model_validate(
        {"day_of_week": 3, "start_time": "20:00", "end_time": "23:00"}
    )
    assert (slot.max_reservations, slot.max_covers) == (10, None)


def test_a_slot_is_named_by_its_id_or_its_day_and_start():
    assert TimeSlotRefIn.model_validate(
        {"day_of_week": 3, "start_time": "20:00"}
    ).start_time == dt.time(20)
    assert "__root__" in errors(TimeSlotRefIn, {"day_of_week": 3})
