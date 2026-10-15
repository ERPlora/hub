"""Input schemas of the appointment app: what a caller (screen, assistant, API key) may send.

Every rule that needs no database lives here, so the 422 names the field: who, what and with whom are
said, a time is a real wall-clock time, a list pages by at most 100, a range is short, a series has a
rule, and the settings stay in range.
"""

import datetime as dt
import uuid

from pydantic import ValidationError

from apps.appointment.schemas import (
    AppointmentCreateIn,
    AppointmentListIn,
    AppointmentRefIn,
    BlockedTimeCreateIn,
    BulkCreateIn,
    BulkDeleteIn,
    CancelIn,
    CheckIn,
    PageIn,
    RecurringCreateIn,
    RecurringUpdateIn,
    RescheduleIn,
    SaleFromAppointmentIn,
    SaleVoidedIn,
    SettingsIn,
    SlotsIn,
    UpdateIn,
)

ID = str(uuid.uuid7())
MONDAY = "2026-10-19"


def errors(schema, **data) -> dict[str, str]:
    """The fields ``schema`` refuses in ``data``, with the first message of each (``__all__`` for the whole)."""
    try:
        schema.model_validate(data)
    except ValidationError as exc:
        out: dict[str, str] = {}
        for error in exc.errors():
            out.setdefault(
                ".".join(str(part) for part in error["loc"]) or "__all__", error["msg"]
            )
        return out
    return {}


BOOKING = {
    "customer": "Lucía",
    "services": [{"service": "Haircut"}],
    "staff": "Ana",
    "start": f"{MONDAY}T10:00",
}


def test_a_page_is_one_to_a_hundred_rows_and_refuses_an_unknown_filter():
    assert PageIn().limit == 50
    assert errors(PageIn, limit=0) and errors(PageIn, limit=101)
    assert "colour" in errors(AppointmentListIn, date_from=MONDAY, colour="red")


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


def test_an_appointment_is_named_by_its_id_or_its_number():
    assert not errors(AppointmentRefIn, id=ID)
    assert not errors(AppointmentRefIn, number="APT-20261019-0001")
    assert "number" in errors(AppointmentRefIn)


def test_a_move_says_what_changes():
    assert not errors(RescheduleIn, number="APT-1", start=f"{MONDAY}T11:00")
    assert not errors(RescheduleIn, number="APT-1", staff="Bea")
    assert "__all__" in errors(RescheduleIn, number="APT-1")
    assert "services" in errors(RescheduleIn, number="APT-1", services=[])


def test_acting_for_the_customer_names_her():
    assert not errors(CancelIn, id=ID, reason="Ill")
    assert "customer" in errors(CancelIn, id=ID, on_behalf_of_customer=True)
    assert not errors(
        CancelIn, id=ID, on_behalf_of_customer=True, customer="+34600111222"
    )
    assert "reason" in errors(CancelIn, id=ID, reason="x" * 501)


def test_an_edit_sends_only_what_changes():
    edit = UpdateIn.model_validate({"id": ID, "notes": "Formula 7/1"})
    assert edit.model_fields_set == {"id", "notes"}
    assert "__all__" in errors(UpdateIn, id=ID)


def test_free_times_take_a_day_and_the_services_or_the_minutes():
    assert not errors(SlotsIn, date=MONDAY, services=["Cut"])
    assert not errors(SlotsIn, date=MONDAY, duration_minutes=45, staff="Ana")
    assert "__all__" in errors(SlotsIn, date=MONDAY)
    assert "__all__" in errors(CheckIn, start=f"{MONDAY}T10:00")


def test_the_agenda_reads_a_short_range():
    assert not errors(AppointmentListIn, date_from=MONDAY, date_to="2026-12-19")
    assert "date_to" in errors(
        AppointmentListIn, date_from=MONDAY, date_to="2026-10-18"
    )
    assert "date_to" in errors(
        AppointmentListIn, date_from=MONDAY, date_to="2027-01-19"
    )


def test_a_bulk_delete_names_one_to_a_hundred_appointments():
    assert not errors(BulkDeleteIn, ids=[ID])
    assert "ids" in errors(BulkDeleteIn, ids=[])
    assert "ids" in errors(BulkDeleteIn, ids=[str(uuid.uuid7()) for _ in range(101)])


def test_a_block_ends_after_it_starts_and_has_a_title():
    good = {"title": "Training", "start": f"{MONDAY}T12:00", "end": f"{MONDAY}T13:00"}
    assert not errors(BlockedTimeCreateIn, **good)
    assert "end" in errors(BlockedTimeCreateIn, **{**good, "end": f"{MONDAY}T11:00"})
    assert "title" in errors(BlockedTimeCreateIn, **{**good, "title": " "})
    # A whole day may end the same day it starts.
    assert not errors(
        BlockedTimeCreateIn, **{**good, "end": f"{MONDAY}T12:00", "all_day": True}
    )


def test_a_series_has_a_rule_and_its_end_is_not_before_its_start():
    series = {
        "customer": "Lucía",
        "services": [{"service": "Cut"}],
        "staff": "Ana",
        "frequency": "weekly",
        "start_date": MONDAY,
        "time": "10:00",
    }
    assert not errors(RecurringCreateIn, **series)
    assert "frequency" in errors(RecurringCreateIn, **{**series, "frequency": "yearly"})
    assert "day_of_week" in errors(RecurringCreateIn, **{**series, "day_of_week": 7})
    assert "end_date" in errors(
        RecurringCreateIn, **{**series, "end_date": "2026-10-01"}
    )
    assert "max_occurrences" in errors(
        RecurringCreateIn, **{**series, "max_occurrences": 0}
    )
    assert "__all__" in errors(RecurringUpdateIn, id=ID, from_date=MONDAY)
    assert not errors(RecurringUpdateIn, id=ID, from_date=MONDAY, time="11:00")


def test_the_settings_stay_in_range():
    assert not errors(SettingsIn, min_booking_notice=0, max_advance_booking=0)
    assert "calendar_end_hour" in errors(SettingsIn, calendar_end_hour=25)
    assert "slot_interval" in errors(SettingsIn, slot_interval=0)
    assert "__all__" in errors(SettingsIn, calendar_start_hour=20, calendar_end_hour=8)
    assert "send_reminders" in errors(SettingsIn, send_reminders=True)


def test_the_sales_payloads_are_read_as_sales_writes_them():
    sale, appointment = str(uuid.uuid7()), str(uuid.uuid7())
    payload = {
        "sale_id": sale,
        "appointment_id": appointment,
        "staff_id": None,
        "total": 2000,
    }
    assert SaleFromAppointmentIn.model_validate(payload).appointment_id == uuid.UUID(
        appointment
    )
    voided = {
        "sale_id": sale,
        "sale_number": "T-1",
        "reason": "x",
        "voided_by": "y",
        "total": 1,
        "lines": [],
    }
    assert SaleVoidedIn.model_validate(voided).sale_id == uuid.UUID(sale)
