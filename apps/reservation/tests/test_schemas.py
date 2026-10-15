"""The inputs of the book's operations: what they accept, what they refuse per field, and how a person
names a reservation, a slot or a waitlist entry (by id, or as said by voice)."""

import datetime as dt

import pytest
from pydantic import ValidationError

from apps.reservation.schemas import (
    BlockedDateIn,
    CustomerEventIn,
    MergedIn,
    ReservationIn,
    ReservationListIn,
    ReservationPatchIn,
    ReservationRefIn,
    SettingsIn,
    SettingsOut,
    TimeSlotIn,
    TimeSlotRefIn,
    WaitlistIn,
)

BOOKING = {"guest_name": "Ana", "date": "2026-10-15", "time": "21:00", "party_size": 4}


def errors(schema, data) -> dict[str, str]:
    with pytest.raises(ValidationError) as caught:
        schema.model_validate(data)
    return {
        ".".join(str(p) for p in e["loc"]) or "__root__": e["msg"]
        for e in caught.value.errors()
    }


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


def test_a_slot_ends_after_it_starts_on_a_weekday():
    assert "end_time" in errors(
        TimeSlotIn, {"day_of_week": 3, "start_time": "21:00", "end_time": "20:00"}
    )
    assert "day_of_week" in errors(
        TimeSlotIn, {"day_of_week": 7, "start_time": "20:00", "end_time": "23:00"}
    )
    assert "max_covers" in errors(
        TimeSlotIn,
        {"day_of_week": 3, "start_time": "20:00", "end_time": "23:00", "max_covers": 0},
    )
    slot = TimeSlotIn.model_validate(
        {"day_of_week": 3, "start_time": "20:00", "end_time": "23:00"}
    )
    assert (slot.max_reservations, slot.max_covers) == (10, None)


def test_a_slot_is_named_by_its_id_or_its_day_and_start():
    assert TimeSlotRefIn.model_validate(
        {"day_of_week": 3, "start_time": "20:00"}
    ).start_time == dt.time(20)
    assert "__root__" in errors(TimeSlotRefIn, {"day_of_week": 3})


def test_a_blocked_window_needs_both_ends_in_order():
    assert BlockedDateIn.model_validate({"date": "2026-10-15"}).is_full_day is True
    assert set(errors(BlockedDateIn, {"date": "2026-10-15", "is_full_day": False})) == {
        "blocked_from",
        "blocked_until",
    }
    assert "blocked_until" in errors(
        BlockedDateIn,
        {
            "date": "2026-10-15",
            "is_full_day": False,
            "blocked_from": "22:00",
            "blocked_until": "21:00",
        },
    )


def test_a_waitlist_entry_says_for_whom():
    entry = {
        "guest_name": "Luis",
        "guest_phone": "600",
        "date": "2026-10-15",
        "preferred_time": "21:00",
        "party_size": 2,
    }
    assert WaitlistIn.model_validate(entry).preferred_time == dt.time(21)
    assert "__root__" in errors(WaitlistIn, {**entry, "guest_name": ""})


def test_the_settings_change_only_what_is_sent_within_their_bounds():
    assert SettingsIn.model_validate({"auto_confirm": True}).model_fields_set == {
        "auto_confirm"
    }
    assert "max_party_size" in errors(SettingsIn, {"max_party_size": 0})
    assert "default_duration_minutes" in errors(
        SettingsIn, {"default_duration_minutes": 24 * 60 + 1}
    )


def test_the_reactions_read_what_they_need_and_ignore_the_rest():
    merged = MergedIn.model_validate(
        {
            "id": "0192f0d4-0000-7000-8000-000000000001",
            "absorbed_id": "0192f0d4-0000-7000-8000-000000000002",
            "x": 1,
        }
    )
    assert str(merged.absorbed_id).endswith("2")
    assert CustomerEventIn.model_validate({"other": True}).id is None


def test_the_days_ahead_say_they_bind_only_the_guest_who_books_herself():
    for schema in (SettingsIn, SettingsOut):
        description = schema.model_fields["max_advance_days"].description
        assert "online" in description and "WhatsApp" in description, schema
