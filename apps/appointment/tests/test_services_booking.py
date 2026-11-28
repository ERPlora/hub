"""Booking one appointment and a batch of them (APPOINTMENT-F01): what a booking freezes and numbers, what it
refuses, and the one event every booking tells.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import NotFound

from apps.appointment.models.numbering import Counter

from .conftest import HUB_DB, MONDAY, assign, at, make_customer, make_day, make_settings, make_shift, run, wall
from .write_checks import actions, book, events, refused

pytestmark = [HUB_DB, pytest.mark.usefixtures("anytime")]


def test_a_booking_freezes_the_customer_and_the_services_and_is_born_confirmed(salon):
    out = run(
        "appointment.appointment.create",
        {
            "customer": "Lucía Pérez",
            "services": [{"service": "Haircut"}, {"service": "Colour"}],
            "staff": "Ana",
            "start": wall(MONDAY, "10:00"),
            "internal_notes": "7/1",
        },
    )
    today = timezone.localdate()
    assert out.number == f"APT-{today:%Y%m%d}-0001"
    assert (out.status, out.source, out.duration_minutes, out.total) == (
        "confirmed",
        "counter",
        90,
        6500,
    )
    assert (out.customer_name, out.customer_phone, out.staff_name) == (
        "Lucía Pérez",
        "+34600111222",
        "Ana López",
    )
    assert out.end == at(MONDAY, "11:30")
    assert [
        (line.name, line.price, line.duration_minutes) for line in out.services
    ] == [
        ("Haircut", 2000, 30),
        ("Colour", 4500, 60),
    ]
    assert actions(out.id) == ["created"]
    assert events("appointment.appointment.created")[0]["number"] == out.number
    # The catalog changing later does not change what was booked.
    salon.cut.price = 9999
    salon.cut.save()
    assert run("appointment.appointment.get", {"id": str(out.id)}).total == 6500


def test_the_numbers_of_a_day_follow_on(salon):
    first = book(salon, "10:00")
    second = book(salon, "11:00")
    assert (first.number[-4:], second.number[-4:]) == ("0001", "0002")
    assert Counter.objects.get(day=timezone.localdate()).last_number == 2


def test_the_professionals_own_price_and_length_are_frozen(salon):
    assign(salon.cut, salon.ana, duration=45, price=2500)
    out = book(salon)
    assert (out.duration_minutes, out.total) == (45, 2500)
    assert book(salon, "12:00", duration_minutes=20).duration_minutes == 20


def test_who_what_and_with_whom_must_be_bookable(salon):
    salon.colour.is_bookable = False
    salon.colour.save()
    refused(
        "appointment.service_not_bookable",
        lambda: book(salon, services=[{"service": "Colour"}]),
    )
    assign(salon.cut, salon.bea)
    refused("appointment.staff_not_eligible", lambda: book(salon))
    salon.bea.is_bookable = False
    salon.bea.save()
    refused(
        "appointment.staff_not_bookable",
        lambda: book(salon, staff_id=str(salon.bea.id)),
    )
    refused("not_found", lambda: book(salon, staff_id=str(uuid.uuid7())), NotFound)
    make_customer("Lucía Pérez", phone="+34600999888")
    refused(
        "customer.customer_ambiguous",
        lambda: book(salon, customer_id=None, customer="Lucía Pérez"),
    )


def test_a_customer_is_named_by_her_phone(salon):
    out = book(salon, customer_id=None, customer="600 111 222")
    assert out.customer_id == salon.lucia.id


def test_a_time_outside_the_hours_is_refused_with_its_reason(salon):
    make_day(0, ("09:00", "14:00"))
    make_shift(salon.ana, (0, "09:00", "13:00"))
    refused("appointment.outside_schedule", lambda: book(salon, "08:00"))
    refused("appointment.outside_staff_hours", lambda: book(salon, "13:00"))
    assert book(salon, "12:30").end == at(MONDAY, "13:00")


def test_overlapping_at_the_front_desk_asks_first_and_books_when_confirmed(salon):
    first = book(salon, "10:00")
    error = refused(
        "appointment.overlap_needs_confirmation", lambda: book(salon, "10:15")
    )
    assert first.number in error.message
    second = book(salon, "10:15", confirm_overlap=True)
    assert second.status == "confirmed"


def test_with_overlapping_off_the_time_is_taken(salon):
    make_settings(allow_overlapping=False)
    book(salon, "10:00")
    refused(
        "appointment.slot_taken", lambda: book(salon, "10:15", confirm_overlap=True)
    )
    # Another professional is free.
    assert book(salon, "10:15", staff_id=str(salon.bea.id)).staff_name == "Bea Ruiz"


def test_the_front_desk_books_in_the_past_the_customer_does_not(salon):
    yesterday = timezone.localdate() - dt.timedelta(days=1)
    assert book(salon, "10:00", day=yesterday).status == "confirmed"
    refused(
        "appointment.in_past",
        lambda: book(salon, "11:00", day=yesterday, source="whatsapp"),
    )
    make_settings(min_booking_notice=60 * 24 * 30)
    refused("appointment.too_soon", lambda: book(salon, "10:00", source="online"))


def test_the_customers_own_booking_is_confirmed_or_pending_by_the_setting(salon):
    online = book(salon, "10:00", source="online")
    assert (online.status, online.booked_by_customer) == ("confirmed", True)
    assert actions(online.id) == ["created", "confirmed"]
    assert len(events("appointment.appointment.confirmed")) == 1
    make_settings(auto_confirm_online=False)
    whatsapp = book(salon, "12:00", source="whatsapp")
    assert whatsapp.status == "pending"
    assert run("appointment.appointment.count_to_confirm").count == 1


def test_the_customer_never_books_on_top_of_another_appointment(salon):
    book(salon, "10:00")
    refused(
        "appointment.slot_taken",
        lambda: book(salon, "10:15", source="online", confirm_overlap=True),
    )



def test_a_batch_books_every_time_or_none(salon):
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(salon.ana.id),
    }
    week = [wall(MONDAY + dt.timedelta(weeks=n), "10:00") for n in range(3)]
    out = run("appointment.appointment.bulk_create", {**data, "starts": week})
    assert len(out.rows) == 3 and len({row.number for row in out.rows}) == 3
    make_settings(allow_overlapping=False)
    clash = [wall(MONDAY, "16:00"), wall(MONDAY, "16:15")]
    error = refused(
        "appointment.slot_taken",
        lambda: run("appointment.appointment.bulk_create", {**data, "starts": clash}),
    )
    assert "16:15" in error.message


def test_every_booking_tells_the_same_created_event_one_per_appointment(salon):
    # An automation listening to «appointment created» works the same for a
    # single booking, a batch and a series, and hears every appointment of a batch or a series.
    book(salon, "10:00")
    batch = [wall(MONDAY + dt.timedelta(weeks=n), "12:00") for n in range(2)]
    run(
        "appointment.appointment.bulk_create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "starts": batch,
        },
    )
    make_settings(max_advance_booking=15)
    series = run(
        "appointment.recurring.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "frequency": "weekly",
            "day_of_week": 0,
            "start_date": MONDAY.isoformat(),
            "time": "16:00",
        },
    )
    created = events("appointment.appointment.created")
    assert len(created) == 1 + len(batch) + series.booked
    assert series.booked >= 1
    assert {tuple(sorted(payload)) for payload in created} == {
        ("customer_id", "customer_name", "id", "number", "staff_id", "start")
    }
    assert {payload["customer_name"] for payload in created} == {"Lucía Pérez"}
