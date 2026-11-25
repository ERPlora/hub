"""The reservations as they are read: the list with its filters, and one by id or as a person says it."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound

from apps.reservation.queries.reservations import get_reservation
from apps.reservation.schemas.reservations import ReservationRefIn

from .conftest import (
    CLOCKS_BACK,
    CLOCKS_FORWARD,
    HUB_DB,
    TODAY,
    TOMORROW,
    ctx_for,
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


def test_the_end_of_a_reservation_is_its_real_end_on_the_wall_clock_the_nights_the_clocks_change():
    back = make_reservation(date=CLOCKS_BACK, time="01:37", duration_minutes=90)
    forward = make_reservation(date=CLOCKS_FORWARD, time="01:30", duration_minutes=90)
    # 90 real minutes: 02:07 of the second pass in October, 04:00 summer time in March.
    assert run("reservation.reservation.get", {"id": str(back.id)}).end_time == dt.time(2, 7)
    assert run("reservation.reservation.get", {"id": str(forward.id)}).end_time == dt.time(4, 0)


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


def test_an_erased_guest_comes_without_a_name():
    make_reservation(guest_name="")
    assert run("reservation.reservation.list").rows[0].guest_name == ""


def test_a_reservation_is_read_by_id_or_by_its_guest_and_day():
    ana = make_reservation(guest_name="Ana García", guest_phone="+34600111222")
    make_reservation(date=TODAY, time="14:00", guest_name="Luis")
    assert run("reservation.reservation.get", {"id": str(ana.id)}).id == ana.id
    assert run("reservation.reservation.get", {"guest": "ana"}).id == ana.id
    assert get_reservation(ctx_for(), ReservationRefIn(guest="ana")).id == ana.id
    assert (
        run(
            "reservation.reservation.get", {"guest": "600111222", "day": "2026-10-15"}
        ).id
        == ana.id
    )


def test_a_guest_with_several_reservations_must_say_which_day():
    make_reservation(guest_name="Ana")
    make_reservation(date=TOMORROW + dt.timedelta(days=1), guest_name="Ana")
    with pytest.raises(Conflict) as caught:
        run("reservation.reservation.get", {"guest": "Ana"})
    assert caught.value.code == "reservation.reservation_ambiguous"
    assert "15/10" in caught.value.message or "2026-10-15" in caught.value.message


def test_a_missing_or_deleted_reservation_is_not_found():
    gone = make_reservation(is_deleted=True)
    for ref in ({"id": str(gone.id)}, {"guest": "Nadie"}):
        with pytest.raises(NotFound) as caught:
            run("reservation.reservation.get", ref)
        assert caught.value.code == "reservation.reservation_not_found"


def test_a_past_reservation_is_found_by_id_and_by_day_but_the_guest_alone_names_the_coming_ones():
    old = make_reservation(date=TODAY - dt.timedelta(days=3), guest_name="Ana")
    coming = make_reservation(guest_name="Ana")
    assert run("reservation.reservation.get", {"guest": "Ana"}).id == coming.id
    assert (
        run("reservation.reservation.get", {"guest": "Ana", "day": str(old.date)}).id
        == old.id
    )


# RESERVATION-F19 — a flow's template prints a value as it comes, with no clock nor formatter: the WhatsApp
# message that confirms a table says «el martes, 5 de marzo de 2030 a las 21:30» because the reservation gives
# its day and its hour ready to read, in the language of whoever asks (not the thread's), as Appointments does.
def test_a_reservation_gives_its_day_and_hour_ready_to_read_in_the_callers_language():
    booked = make_reservation(date=dt.date(2030, 3, 5), time="21:30", status="confirmed")
    spanish = run("reservation.reservation.get", {"id": str(booked.id)}, ctx_for(language="es"))
    assert (spanish.date_label, spanish.time_label) == ("martes, 5 de marzo de 2030", "21:30")
    english = run("reservation.reservation.get", {"id": str(booked.id)}, ctx_for(language="en"))
    assert (english.date_label, english.time_label) == ("Tuesday, March 5, 2030", "21:30")
    listed = run(
        "reservation.reservation.list", {"date_from": "2030-03-05"}, ctx_for(language="es")
    )
    assert (listed.rows[0].date_label, listed.rows[0].time_label) == (
        "martes, 5 de marzo de 2030",
        "21:30",
    )


def test_the_day_and_hour_ready_to_read_are_the_wall_clock_whatever_the_zone():
    """A reservation keeps the business's wall clock: a 23:30 table stays on its day and its hour, east or
    west of UTC."""
    late = make_reservation(date=dt.date(2030, 3, 5), time="23:30")
    for zone in ("Pacific/Auckland", "Pacific/Honolulu"):
        with timezone.override(zone):
            read = run("reservation.reservation.get", {"id": str(late.id)})
        assert (read.date_label, read.time_label) == ("Tuesday, March 5, 2030", "23:30")
