"""The book's list (``reservation.reservation.list``): the reservations of some days or, searching, of the whole
book, filtered, sorted and paged."""

import datetime as dt

from .conftest import (
    HUB_DB,
    TODAY,
    TOMORROW,
    make_customer,
    make_reservation,
    make_table,
    make_zone,
    run,
)

pytestmark = HUB_DB


def test_the_list_gives_a_day_by_time_with_its_table_and_its_end():
    table = make_table("5", zone=make_zone("Terrace"))
    late = make_reservation(time="22:00", table=table, party_size=4)
    early = make_reservation(time="20:30", duration_minutes=90)
    make_reservation(date=TODAY, time="14:00")
    result = run(
        "reservation.reservation.list",
        {"date_from": "2026-10-15", "date_to": "2026-10-15"},
    )
    assert [row.id for row in result.rows] == [early.id, late.id]
    assert result.total == 2
    row = result.rows[1]
    assert (row.table_label, row.table_capacity, row.end_time) == (
        "5 (Terrace)",
        4,
        dt.time(0, 0),
    )
    assert (result.rows[0].table_label, result.rows[0].end_time) == ("", dt.time(22, 0))


def test_the_list_hides_the_deleted_and_filters_by_status_table_customer_party_and_time():
    table = make_table("5")
    card = make_customer("Marta")
    make_reservation(
        time="20:00", status="confirmed", table=table, party_size=2, customer_id=card.id
    )
    make_reservation(time="21:00", status="cancelled", party_size=6)
    make_reservation(time="21:30", is_deleted=True)

    def times(**filters):
        return [
            f"{row.time:%H:%M}"
            for row in run("reservation.reservation.list", filters).rows
        ]

    assert times() == ["20:00", "21:00"]
    assert times(status="cancelled") == ["21:00"]
    assert times(table_id=str(table.id)) == ["20:00"]
    assert times(customer_id=str(card.id)) == ["20:00"]
    assert times(party_size_from=3) == ["21:00"]
    assert times(party_size_to=3) == ["20:00"]
    assert times(time="21") == ["21:00"]


def test_the_list_filters_by_part_of_the_guests_name_and_by_days():
    make_reservation(guest_name="Ana García")
    make_reservation(date=TOMORROW + dt.timedelta(days=2), guest_name="Luis Pérez")

    def guests(**filters):
        return [row.guest_name for row in run("reservation.reservation.list", filters).rows]

    assert guests(guest_name="garcía") == ["Ana García"]
    assert guests(date_from=(TOMORROW + dt.timedelta(days=1)).isoformat()) == ["Luis Pérez"]
    assert guests(date_to=TOMORROW.isoformat()) == ["Ana García"]


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


def test_an_erased_guest_comes_without_a_name():
    make_reservation(guest_name="")
    assert run("reservation.reservation.list").rows[0].guest_name == ""
