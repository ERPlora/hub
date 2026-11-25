"""The inputs of the reservations: what a booking accepts, what it refuses per field, how a person names a
reservation (by id, or as said by voice) and what a change or the book's list take."""

import datetime as dt

from apps.reservation.schemas.reservations import (
    ReservationIn,
    ReservationListIn,
    ReservationPatchIn,
    ReservationRefIn,
)

from .conftest import errors

BOOKING = {"guest_name": "Ana", "date": "2026-10-15", "time": "21:00", "party_size": 4}


def test_a_booking_reads_the_day_and_the_wall_clock_time_and_defaults_the_rest():
    booking = ReservationIn.model_validate(BOOKING)
    assert (booking.date, booking.time, booking.party_size) == (
        dt.date(2026, 10, 15),
        dt.time(21, 0),
        4,
    )
    assert (
        booking.source,
        booking.duration_minutes,
        booking.table_id,
        booking.notes,
    ) == ("phone", None, None, "")


def test_a_booking_says_for_whom():
    assert "__root__" in errors(ReservationIn, {**BOOKING, "guest_name": ""})
    assert (
        ReservationIn.model_validate(
            {**BOOKING, "guest_name": "", "customer": "600111222"}
        ).customer
        == "600111222"
    )


def test_a_booking_refuses_an_empty_party_a_waitlist_source_and_a_field_it_does_not_know():
    assert "party_size" in errors(ReservationIn, {**BOOKING, "party_size": 0})
    assert "source" in errors(ReservationIn, {**BOOKING, "source": "waitlist"})
    assert "duration_minutes" in errors(
        ReservationIn, {**BOOKING, "duration_minutes": 0}
    )
    assert "status" in errors(ReservationIn, {**BOOKING, "status": "confirmed"})


def test_a_reservation_is_named_by_its_id_or_by_its_guest_and_day():
    assert (
        ReservationRefIn.model_validate({"guest": "Ana", "day": "2026-10-15"}).guest
        == "Ana"
    )
    assert "__root__" in errors(ReservationRefIn, {})


def test_a_change_sends_only_what_changes_and_can_drop_the_table():
    patch = ReservationPatchIn.model_validate(
        {"id": "0192f0d4-0000-7000-8000-000000000001", "time": "22:00"}
    )
    assert patch.model_fields_set == {"id", "time"}
    assert (
        ReservationPatchIn.model_validate({"guest": "Ana", "no_table": True}).no_table
        is True
    )


def test_a_list_pages_up_to_one_hundred_and_refuses_an_unknown_filter():
    assert ReservationListIn.model_validate({}).sort == "starts_at"
    assert "limit" in errors(ReservationListIn, {"limit": 101})
    assert "colour" in errors(ReservationListIn, {"colour": "red"})
