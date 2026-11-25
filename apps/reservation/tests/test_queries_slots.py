"""The slots the book takes reservations in, as they are listed."""

from apps.reservation.queries.slots import list_slots
from apps.reservation.schemas.slots import TimeSlotListIn

from .conftest import HUB_DB, THURSDAY, ctx_for, make_slot, run

pytestmark = HUB_DB


def test_the_slots_list_by_weekday_and_start_without_the_deleted():
    dinner = make_slot(THURSDAY, "20:00", "23:30")
    lunch = make_slot(THURSDAY, "13:00", "16:00")
    monday = make_slot(0, "13:00", "16:00", max_covers=30)
    make_slot(1, "13:00", "16:00", is_deleted=True)
    assert [row.id for row in run("reservation.time_slot.list").rows] == [
        monday.id,
        lunch.id,
        dinner.id,
    ]
    assert [
        row.id
        for row in run("reservation.time_slot.list", {"day_of_week": THURSDAY}).rows
    ] == [
        lunch.id,
        dinner.id,
    ]
    assert (
        run("reservation.time_slot.list", {"day_of_week": 0}).rows[0].max_covers == 30
    )
    assert [row.id for row in list_slots(ctx_for(), TimeSlotListIn(day_of_week=0)).rows] == [monday.id]
