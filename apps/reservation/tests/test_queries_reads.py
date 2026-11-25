"""What the book's lists share: finding a guest as a person says her, and the pages."""

import datetime as dt

from apps.reservation.models import Reservation
from apps.reservation.queries.reads import _guest_matches

from .conftest import HUB_DB, TODAY, TOMORROW, ctx_for, make_reservation, run

pytestmark = HUB_DB


def test_searching_looks_through_the_whole_book_by_name_phone_however_typed_or_email():
    make_reservation(guest_name="Ana García", guest_phone="+34600111222")
    make_reservation(
        date=TOMORROW + dt.timedelta(days=7),
        guest_name="Luis",
        guest_email="luis@bar.es",
    )
    assert [
        row.guest_name
        for row in run("reservation.reservation.list", {"search": "garcía"}).rows
    ] == ["Ana García"]
    assert [
        row.guest_name
        for row in run("reservation.reservation.list", {"search": "600 111 222"}).rows
    ] == ["Ana García"]
    assert [
        row.guest_name
        for row in run("reservation.reservation.list", {"search": "bar.es"}).rows
    ] == ["Luis"]
    assert Reservation.objects.get(_guest_matches(ctx_for(), "600 111 222")).guest_name == "Ana García"


def test_the_list_sorts_in_calendar_order_and_pages():
    for day, at in ((TOMORROW, "22:00"), (TODAY, "21:00"), (TOMORROW, "13:00")):
        make_reservation(date=day, time=at)
    result = run("reservation.reservation.list", {"limit": 2})
    assert [(row.date, f"{row.time:%H:%M}") for row in result.rows] == [
        (TODAY, "21:00"),
        (TOMORROW, "13:00"),
    ]
    assert (result.total, result.limit, result.offset) == (3, 2, 0)
    backwards = run("reservation.reservation.list", {"sort": "-starts_at", "limit": 1})
    assert [(row.date, f"{row.time:%H:%M}") for row in backwards.rows] == [
        (TOMORROW, "22:00")
    ]
