"""The days or hours the book takes no reservations (``reservation.blocked_date.list``)."""

import datetime as dt

from .conftest import HUB_DB, TOMORROW, make_blocked, run

pytestmark = HUB_DB


def test_the_blocked_dates_list_by_date_without_the_deleted():
    later = make_blocked(TOMORROW + dt.timedelta(days=5), reason="Holiday")
    soon = make_blocked(
        TOMORROW,
        reason="Event",
        is_full_day=False,
        blocked_from=dt.time(20),
        blocked_until=dt.time(23),
    )
    make_blocked(TOMORROW + dt.timedelta(days=9), is_deleted=True)
    assert [row.id for row in run("reservation.blocked_date.list").rows] == [
        soon.id,
        later.id,
    ]
    assert [
        row.id
        for row in run("reservation.blocked_date.list", {"is_full_day": True}).rows
    ] == [later.id]
    assert [
        row.id
        for row in run("reservation.blocked_date.list", {"date_to": "2026-10-16"}).rows
    ] == [soon.id]
