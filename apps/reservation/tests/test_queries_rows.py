"""What a read answers of a reservation: its end on the wall clock, and its day and hour ready to read."""

import datetime as dt

from django.utils import timezone

from .conftest import CLOCKS_BACK, CLOCKS_FORWARD, HUB_DB, ctx_for, make_reservation, run

pytestmark = HUB_DB


def test_the_end_of_a_reservation_is_its_real_end_on_the_wall_clock_the_nights_the_clocks_change():
    back = make_reservation(date=CLOCKS_BACK, time="01:37", duration_minutes=90)
    forward = make_reservation(date=CLOCKS_FORWARD, time="01:30", duration_minutes=90)
    # 90 real minutes: 02:07 of the second pass in October, 04:00 summer time in March.
    assert run("reservation.reservation.get", {"id": str(back.id)}).end_time == dt.time(2, 7)
    assert run("reservation.reservation.get", {"id": str(forward.id)}).end_time == dt.time(4, 0)


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
