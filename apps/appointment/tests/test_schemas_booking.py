"""Booking: who, what and with whom are said, and a time is a real wall-clock time."""

import datetime as dt

from apps.appointment.schemas.booking import AppointmentCreateIn, BulkCreateIn

from .schema_checks import ID, MONDAY, errors

BOOKING = {
    "customer": "Lucía",
    "services": [{"service": "Haircut"}],
    "staff": "Ana",
    "start": f"{MONDAY}T10:00",
}


def test_a_booking_names_the_customer_the_services_and_the_professional():
    assert not errors(AppointmentCreateIn, **BOOKING)
    booking = AppointmentCreateIn.model_validate(BOOKING)
    assert (booking.source, booking.confirm_overlap, booking.duration_minutes) == (
        "counter",
        False,
        None,
    )
    assert "customer" in errors(AppointmentCreateIn, **{**BOOKING, "customer": None})
    assert "staff" in errors(AppointmentCreateIn, **{**BOOKING, "staff": None})
    assert "services" in errors(AppointmentCreateIn, **{**BOOKING, "services": []})
    assert "services.0.service" in errors(AppointmentCreateIn, **{**BOOKING, "services": [{}]})
    # An id is enough on its own.
    assert not errors(
        AppointmentCreateIn,
        customer_id=ID,
        services=[{"service_id": ID}],
        staff_id=ID,
        start=f"{MONDAY}T10:00",
    )


def test_a_time_is_a_wall_clock_time_or_an_instant_and_a_booking_lasts_at_most_a_day():
    naive = AppointmentCreateIn.model_validate({**BOOKING, "start": f"{MONDAY} 10:00"})
    assert naive.start == dt.datetime(2026, 10, 19, 10, 0)
    assert "start" in errors(
        AppointmentCreateIn, **{**BOOKING, "start": "tomorrow at ten"}
    )
    assert "duration_minutes" in errors(
        AppointmentCreateIn, **{**BOOKING, "duration_minutes": 0}
    )
    assert "duration_minutes" in errors(
        AppointmentCreateIn, **{**BOOKING, "duration_minutes": 1441}
    )
    assert "source" in errors(AppointmentCreateIn, **{**BOOKING, "source": "fax"})


def test_a_batch_books_one_to_fifty_times():
    times = [f"{MONDAY}T{hour:02d}:00" for hour in range(9, 12)]
    assert not errors(BulkCreateIn, **{**BOOKING, "start": None, "starts": times})
    assert "starts" in errors(
        BulkCreateIn,
        customer="Lucía",
        services=[{"service": "Cut"}],
        staff="Ana",
        starts=[],
    )
    assert "starts" in errors(
        BulkCreateIn,
        customer="Lucía",
        services=[{"service": "Cut"}],
        staff="Ana",
        starts=times * 17,
    )
