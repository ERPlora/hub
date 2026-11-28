"""Writes of the waitlist (``reservation.waitlist.*``): writing somebody on it, marking her contacted, turning her
entry into a reservation and taking it off."""

import datetime as dt

from apps.reservation.models import Reservation, WaitlistEntry

from .conftest import (
    EMPLOYEE,
    HUB_DB,
    NOW,
    THURSDAY,
    ctx_for,
    events,
    make_entry,
    make_reservation,
    make_slot,
    refusal,
    run,
    set_rules,
)

pytestmark = HUB_DB


def test_the_host_writes_somebody_on_the_waitlist_and_marks_her_contacted():
    entry = run(
        "reservation.waitlist.create",
        {
            "guest_name": "Luis",
            "guest_phone": "600333444",
            "date": "2026-10-15",
            "preferred_time": "21:00",
            "party_size": 3,
            "notes": "Window, please",
        },
        ctx_for(EMPLOYEE),
    )
    assert (
        entry.guest_name,
        entry.party_size,
        entry.notes,
        entry.is_contacted,
        entry.is_converted,
    ) == ("Luis", 3, "Window, please", False, False)
    contacted = run(
        "reservation.waitlist.update",
        {"id": str(entry.id), "is_contacted": True, "notes": "Called"},
        ctx_for(EMPLOYEE),
    )
    assert (contacted.is_contacted, contacted.contacted_at, contacted.notes) == (
        True,
        NOW,
        "Called",
    )
    assert events() == ["reservation.waitlist.created", "reservation.waitlist.updated"]


def test_the_waitlist_takes_somebody_without_a_phone():
    # Market (duda 7): a waitlist has no required contact; the phone is only for calling back.
    entry = run(
        "reservation.waitlist.create",
        {"guest_name": "Luis", "date": "2026-10-15", "preferred_time": "21:00", "party_size": 2},
    )
    assert (entry.guest_name, entry.guest_phone, entry.customer_id) == ("Luis", "", None)


def test_converting_an_entry_books_its_own_data_and_links_it(week):
    set_rules(default_duration_minutes=100)
    entry = make_entry(time="21:15", party_size=30, notes="Terrace")
    converted = run(
        "reservation.waitlist.convert", {"id": str(entry.id)}, ctx_for(EMPLOYEE)
    )
    reservation = converted.reservation
    assert (
        reservation.guest_name,
        reservation.party_size,
        reservation.time,
        reservation.duration_minutes,
    ) == (
        "Luis Pérez",
        30,
        dt.time(21, 15),
        100,
    )
    assert (
        reservation.source,
        reservation.status,
        reservation.notes,
        reservation.waitlist_entry_id,
    ) == (
        "waitlist",
        "pending",
        "Terrace",
        entry.id,
    )
    assert (converted.entry.is_converted, converted.entry.reservation_id) == (
        True,
        reservation.id,
    )
    assert events() == [
        "reservation.reservation.created",
        "reservation.waitlist.converted",
    ]
    error = refusal(lambda: run("reservation.waitlist.convert", {"id": str(entry.id)}))
    assert (error.code, error.message) == (
        "reservation.waitlist_converted",
        "This entry was already converted into a reservation.",
    )


def test_a_conversion_into_a_full_slot_changes_nothing():
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    make_reservation()
    entry = make_entry()
    assert (
        refusal(lambda: run("reservation.waitlist.convert", {"id": str(entry.id)})).code
        == "reservation.no_capacity"
    )
    assert WaitlistEntry.objects.get(pk=entry.id).reservation_id is None
    assert Reservation.objects.count() == 1


def test_an_entry_leaves_the_waitlist():
    entry = make_entry()
    run("reservation.waitlist.delete", {"guest": "Luis"})
    assert WaitlistEntry.objects.get(pk=entry.id).is_deleted is True
    assert events() == ["reservation.waitlist.deleted"]
