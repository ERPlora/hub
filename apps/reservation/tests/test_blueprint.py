"""What of Reservations travels in an export of the business (BASE-F35): the book's time slots and its blocked days,
read with Reservations' own lists and written with its own creates, so that loading the file brings the book's hours
back as they were. The reservations and the waiting list are what already happened: they never travel.

Every test runs against the real apps, in business A's own database, as production does.
"""

import datetime as dt

from apps.reservation.tests.conftest import HUB_DB, in_business_a
from base.tests.blueprint_round_trip import app_report, call, ctx, data_of, exported, loaded_back

__all__ = ["ctx", "in_business_a"]
pytestmark = HUB_DB

DINNER = {"day_of_week": 4, "start_time": dt.time(20, 0), "end_time": dt.time(23, 30), "max_reservations": 12,
          "max_covers": 40}  # fmt: skip
LUNCH = {"day_of_week": 5, "start_time": dt.time(13, 0), "end_time": dt.time(16, 0), "max_reservations": 8,
         "max_covers": None}  # fmt: skip
CHRISTMAS = {"date": dt.date(2026, 12, 25), "reason": "Christmas", "is_full_day": True, "blocked_from": None,
             "blocked_until": None}  # fmt: skip
PRIVATE = {"date": dt.date(2026, 11, 20), "reason": "Private event", "is_full_day": False,
           "blocked_from": dt.time(20, 0), "blocked_until": dt.time(23, 0)}  # fmt: skip


def a_book(ctx):
    for slot in (DINNER, LUNCH):
        call(ctx, "reservation.time_slot.create", **slot)
    for block in (CHRISTMAS, PRIVATE):
        call(ctx, "reservation.blocked_date.create", **block)


def the_book(ctx) -> dict:
    """The book's slots and blocked days as the business reads them, without ids."""
    slots = sorted(
        tuple(getattr(row, name) for name in DINNER) for row in call(ctx, "reservation.time_slot.list", limit=100).rows
    )
    blocks = sorted(
        tuple(getattr(row, name) for name in CHRISTMAS)
        for row in call(ctx, "reservation.blocked_date.list", limit=100).rows
    )
    return {"slots": slots, "blocked": blocks}


def emptied(ctx) -> None:
    for row in call(ctx, "reservation.time_slot.list", limit=100).rows:
        call(ctx, "reservation.time_slot.delete", id=row.id)
    for row in call(ctx, "reservation.blocked_date.list", limit=100).rows:
        call(ctx, "reservation.blocked_date.delete", id=row.id)


def test_a_backup_brings_the_book_s_slots_and_blocked_days_back(ctx):
    a_book(ctx)
    before = the_book(ctx)
    file = exported(ctx, ["reservation"])
    emptied(ctx)

    report = loaded_back(ctx, file)

    assert the_book(ctx) == before
    assert {part["key"]: part["created"] for part in app_report(report, "reservation")["datasets"]} == {
        "reservation.time_slot": 2,
        "reservation.blocked_date": 2,
    }


def test_loading_the_file_again_duplicates_nothing(ctx):
    a_book(ctx)
    file = exported(ctx, ["reservation"])

    report = loaded_back(ctx, file)

    assert [(part["created"], part["already"]) for part in app_report(report, "reservation")["datasets"]] == [
        (0, 2),
        (0, 2),
    ]


def test_the_reservations_themselves_never_travel(ctx):
    a_book(ctx)

    assert set(data_of(ctx, ["reservation"])) == {"reservation.time_slot", "reservation.blocked_date"}
