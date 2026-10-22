"""The book's writes: taking, changing and moving a reservation through its states, the slots, the blocked
dates, the waitlist, the rules and the reactions to Customers. Each one is one transaction with its events
in the outbox; a refusal writes nothing and announces nothing.

What the table app does with each change (holds, the check opened when seating) is
``test_integration_table.py``; the customer cards, ``test_integration_customer.py``; the opening hours,
``test_integration_schedule.py``.
"""

import datetime as dt

import pytest
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.reservation.models import (
    BlockedDate,
    Reservation,
    Settings,
    TimeSlot,
    WaitlistEntry,
)

from .conftest import (
    A,
    NOW,
    THURSDAY,
    TOMORROW,
    book,
    ctx_for,
    make_blocked,
    make_entry,
    make_reservation,
    make_slot,
    make_table,
    open_week,
    pin_clock,
    run,
    set_rules,
)

pytestmark = pytest.mark.django_db

EMPLOYEE = "hub_employee"
MANAGER = "hub_manager"


def events(prefix: str = "reservation.") -> list[str]:
    return list(
        OutboxEvent.objects.filter(name__startswith=prefix)
        .order_by("created_at", "id")
        .values_list("name", flat=True)
    )


def payload(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).latest("created_at", "id").payload


def refusal(call) -> Conflict:
    with pytest.raises(Conflict) as caught:
        call()
    return caught.value


@pytest.fixture
def week(db):
    open_week()


# ── Taking a reservation (F06) ───────────────────────────────────────────────────────────────────


def test_a_reservation_is_taken_pending_for_the_default_duration(week):
    set_rules(default_duration_minutes=90)
    out = book(
        party_size=4, notes="Birthday", internal_notes="Wheelchair", source="in_person"
    )
    reservation = Reservation.objects.get(pk=out.id)
    assert (
        reservation.status,
        reservation.party_size,
        reservation.duration_minutes,
    ) == ("pending", 4, 90)
    assert (reservation.date, reservation.time, reservation.source) == (
        TOMORROW,
        dt.time(21, 0),
        "in_person",
    )
    assert (reservation.notes, reservation.internal_notes, reservation.created_by) == (
        "Birthday",
        "Wheelchair",
        "tester",
    )
    assert out.end_time == dt.time(22, 30)
    assert events() == ["reservation.reservation.created"]
    assert payload("reservation.reservation.created") == {
        "id": str(out.id),
        "status": "pending",
        "table_id": None,
        "date": "2026-10-15",
        "time": "21:00",
        "party_size": 4,
    }


def test_with_automatic_confirmation_it_is_born_confirmed_and_says_so(week):
    set_rules(auto_confirm=True)
    out = book()
    assert (out.status, out.confirmed_at) == ("confirmed", NOW)
    assert events() == [
        "reservation.reservation.created",
        "reservation.reservation.status_changed",
    ]
    changed = payload("reservation.reservation.status_changed")
    assert (changed["status"], changed["previous_status"], changed["guest_name"]) == (
        "confirmed",
        None,
        "Ana García",
    )


@pytest.mark.parametrize(
    ("change", "data", "code", "field"),
    [
        ({}, {"guest_phone": ""}, "reservation.phone_required", "guest_phone"),
        ({"require_email": True}, {}, "reservation.email_required", "guest_email"),
        (
            {"max_party_size": 6},
            {"party_size": 7, "source": "online"},
            "reservation.party_size_exceeded",
            "party_size",
        ),
        ({}, {"date": "2026-10-14", "time": "11:00"}, "reservation.in_past", "time"),
        (
            {},
            {"source": "online", "date": "2026-10-14", "time": "12:30"},
            "reservation.too_soon",
            "time",
        ),
        (
            {"max_advance_days": 5},
            {"date": "2026-10-21", "source": "online"},
            "reservation.too_far",
            "date",
        ),
        ({}, {"time": "18:00"}, "reservation.no_service_day", "time"),
    ],
)
def test_the_gate_refuses_with_its_reason_on_its_field_and_writes_nothing(
    week, change, data, code, field
):
    set_rules(**change)
    error = refusal(lambda: book(**data))
    assert error.code == code
    assert error.fields == {field: error.message}
    assert Reservation.objects.count() == 0
    assert events() == []


def test_the_reasons_read_as_people_say_them(week):
    set_rules(max_party_size=6)
    assert refusal(lambda: book(party_size=7, source="online")).message == (
        "That party size is outside the limits of this business (1–6 guests)."
    )
    assert (
        refusal(lambda: book(guest_phone="")).message
        == "This business requires a phone number for every reservation."
    )
    make_blocked(reason="Holiday")
    assert (
        refusal(lambda: book()).message
        == "That date is blocked (holiday or closure): no reservations are taken then."
    )


def test_a_blocked_date_and_a_full_slot_refuse(week):
    make_blocked(is_full_day=False, blocked_from=dt.time(20), blocked_until=dt.time(21))
    assert refusal(lambda: book(time="20:30")).code == "reservation.date_blocked"
    assert book(time="21:30").status == "pending"


def test_the_last_place_of_a_slot_goes_to_one_reservation():
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    book(time="20:00")
    error = refusal(
        lambda: book(time="22:00", guest_name="Luis", guest_phone="600333444")
    )
    assert (error.code, error.message) == (
        "reservation.no_capacity",
        "That time slot is fully booked for that date.",
    )


def test_the_staff_book_a_full_slot_knowingly():
    make_slot(THURSDAY, "13:00", "16:00", max_reservations=1)
    book(time="13:00")
    error = refusal(lambda: book(time="14:00", guest_name="Luis", guest_phone="600333444"))
    assert error.code == "reservation.no_capacity"
    overbooked = book(time="14:00", guest_name="Luis", guest_phone="600333444", overbook=True)
    assert overbooked.status == "pending"
    online = refusal(
        lambda: book(time="14:00", guest_name="Eva", guest_phone="600444555", source="online", overbook=True)
    )
    assert online.code == "reservation.no_capacity"


def test_the_online_limits_do_not_bind_the_staff(week):
    set_rules(max_party_size=8, max_advance_days=30)
    assert book(party_size=30).party_size == 30
    assert book(date="2027-05-13", guest_name="Boda", guest_phone="600555666").date == dt.date(2027, 5, 13)


def test_a_full_slot_tells_the_staff_they_may_book_it_anyway_and_never_the_guest():
    # The API and the assistant read it from the refusal: `overbook` is the input that books it anyway.
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    book(time="20:00")
    staff = refusal(lambda: book(time="21:00", guest_name="Luis", guest_phone="600333444"))
    assert staff.fields == {
        "time": "That time slot is fully booked for that date.",
        "overbook": "Send overbook as true to book this full slot anyway.",
    }
    online = refusal(lambda: book(time="21:00", guest_name="Eva", guest_phone="600444555", source="online"))
    assert online.fields == {"time": "That time slot is fully booked for that date."}


def test_a_slot_that_limits_covers_refuses_a_party_that_does_not_fit():
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=10, max_covers=6)
    book(party_size=4)
    assert (
        refusal(
            lambda: book(party_size=3, guest_name="Luis", guest_phone="600333444")
        ).code
        == "reservation.no_capacity"
    )
    assert (
        book(party_size=2, guest_name="Luis", guest_phone="600333444").party_size == 2
    )


def test_a_table_out_of_service_or_already_booked_then_refuses(week):
    blocked = make_table("6", blocked=True)
    error = refusal(lambda: book(table_id=str(blocked.id)))
    assert (error.code, error.fields) == (
        "reservation.table_unavailable",
        {"table_id": error.message},
    )
    five = make_table("5")
    book(table="5")
    error = refusal(
        lambda: book(
            table_id=str(five.id),
            time="22:30",
            guest_name="Luis",
            guest_phone="600333444",
        )
    )
    assert error.code == "reservation.table_taken"
    assert (
        error.message
        == "Table 5 (no zone) already has a reservation from 21:00 to 23:00."
    )
    assert (
        book(
            table_id=str(five.id),
            time="23:00",
            guest_name="Luis",
            guest_phone="600333444",
        ).table_label
        == "5 (no zone)"
    )


def test_a_table_said_by_its_number_that_does_not_exist_is_not_found(week):
    with pytest.raises(NotFound) as caught:
        book(table="99")
    assert caught.value.code == "table.table_not_found"


def test_taking_a_reservation_needs_its_permission(week):
    with pytest.raises(PermissionDenied):
        book(ctx=ctx_for(permissions=set()))
    assert book(ctx=ctx_for(EMPLOYEE)).status == "pending"


# ── Changing a reservation (F08) ─────────────────────────────────────────────────────────────────


def test_a_change_moves_what_is_sent_through_the_same_gate_without_counting_itself():
    make_slot(THURSDAY, "20:00", "23:30", max_reservations=1)
    out = book(time="20:00")
    changed = run(
        "reservation.reservation.update",
        {"id": str(out.id), "time": "21:30", "party_size": 6, "notes": "Window"},
    )
    assert (changed.time, changed.party_size, changed.notes, changed.guest_name) == (
        dt.time(21, 30),
        6,
        "Window",
        "Ana García",
    )
    assert events()[-1] == "reservation.reservation.updated"
    assert payload("reservation.reservation.updated") == {
        "id": str(out.id),
        "time": "21:30",
        "party_size": 6,
    }


def test_a_change_is_refused_with_its_reason_and_leaves_the_reservation_as_it_was(week):
    out = book()
    error = refusal(
        lambda: run(
            "reservation.reservation.update", {"id": str(out.id), "time": "18:00"}
        )
    )
    assert error.code == "reservation.no_service_day"
    assert Reservation.objects.get(pk=out.id).time == dt.time(21, 0)


def test_a_reservation_under_way_still_gets_one_more_guest(week, monkeypatch):
    out = book(time="13:00", date="2026-10-14")
    pin_clock(monkeypatch, dt.datetime(2026, 10, 14, 11, 30, tzinfo=dt.UTC))
    changed = run("reservation.reservation.update", {"id": str(out.id), "party_size": 5})
    assert changed.party_size == 5


def test_a_finished_reservation_only_changes_its_notes(week):
    seated = make_reservation(status="seated")
    assert (
        run(
            "reservation.reservation.update",
            {"id": str(seated.id), "internal_notes": "VIP"},
        ).internal_notes
        == "VIP"
    )
    error = refusal(
        lambda: run(
            "reservation.reservation.update", {"id": str(seated.id), "party_size": 3}
        )
    )
    assert (error.code, error.message) == (
        "reservation.not_editable",
        "This reservation can no longer change: only its notes.",
    )


def test_a_change_by_voice_names_the_reservation_by_its_guest_and_day(week):
    book()
    changed = run(
        "reservation.reservation.update",
        {"guest": "Ana", "day": "2026-10-15", "time": "22:00"},
    )
    assert changed.time == dt.time(22, 0)


# ── Its states (F07, F09–F12) ────────────────────────────────────────────────────────────────────


def test_the_confirmation_answers_with_its_day_and_hour_ready_to_read_in_the_callers_language(week):
    """RESERVATION-F19: what confirms a table can say it back («jueves, 15 de octubre de 2026 a las 21:00»)."""
    out = book()
    confirmed = run("reservation.reservation.confirm", {"id": str(out.id)}, ctx_for(language="es"))
    assert (confirmed.date_label, confirmed.time_label) == ("jueves, 15 de octubre de 2026", "21:00")


def test_the_states_only_move_forward_and_stamp_their_time(week):
    out = book()
    confirmed = run("reservation.reservation.confirm", {"id": str(out.id)})
    assert (confirmed.status, confirmed.confirmed_at) == ("confirmed", NOW)
    seated = run("reservation.reservation.seat", {"id": str(out.id)})
    assert (seated.status, seated.seated_at, seated.table_session_id) == (
        "seated",
        NOW,
        None,
    )
    completed = run("reservation.reservation.complete", {"id": str(out.id)})
    assert (completed.status, completed.completed_at) == ("completed", NOW)
    assert events().count("reservation.reservation.status_changed") == 3
    last = payload("reservation.reservation.status_changed")
    assert (last["status"], last["previous_status"]) == ("completed", "seated")


@pytest.mark.parametrize(
    ("current", "action", "message"),
    [
        (
            "pending",
            "complete",
            "This reservation is pending: it cannot be completed before it is seated.",
        ),
        (
            "confirmed",
            "confirm",
            "This reservation is confirmed: it cannot be confirmed.",
        ),
        ("seated", "cancel", "This reservation is seated: it cannot be cancelled."),
        ("seated", "seat", "This reservation is seated: it cannot be seated."),
        (
            "cancelled",
            "confirm",
            "This reservation is cancelled: its status can no longer change.",
        ),
        (
            "completed",
            "cancel",
            "This reservation is completed: its status can no longer change.",
        ),
        (
            "no_show",
            "no_show",
            "This reservation is no-show: its status can no longer change.",
        ),
    ],
)
def test_an_illegal_step_is_refused_naming_the_current_status(current, action, message):
    reservation = make_reservation(status=current)
    error = refusal(
        lambda: run(f"reservation.reservation.{action}", {"id": str(reservation.id)})
    )
    assert (error.code, error.message) == ("reservation.illegal_transition", message)
    assert events() == []


def test_cancelling_keeps_the_reason_and_frees_the_place(week):
    make_slot(THURSDAY, "13:00", "16:00", max_reservations=1)
    out = book(time="13:00")
    cancelled = run(
        "reservation.reservation.cancel", {"id": str(out.id), "reason": "Ill"}
    )
    assert (
        cancelled.status,
        cancelled.cancelled_at,
        cancelled.cancellation_reason,
    ) == ("cancelled", NOW, "Ill")
    assert (
        book(time="13:30", guest_name="Luis", guest_phone="600333444").status
        == "pending"
    )


def test_a_no_show_is_marked_and_frees_the_place(week):
    out = book()
    marked = run("reservation.reservation.no_show", {"id": str(out.id)})
    assert (marked.status, marked.no_show_at) == ("no_show", NOW)


def test_the_host_at_the_door_confirms_seats_and_cancels(week):
    out = book()
    host = ctx_for(EMPLOYEE)
    assert (
        run("reservation.reservation.confirm", {"id": str(out.id)}, host).status
        == "confirmed"
    )
    assert (
        run("reservation.reservation.cancel", {"id": str(out.id)}, host).status
        == "cancelled"
    )


# ── Deleting (F20) and releasing the unconfirmed (F13) ───────────────────────────────────────────


def test_only_the_admin_deletes_and_the_reservation_leaves_the_book(week):
    out = book()
    with pytest.raises(PermissionDenied):
        run("reservation.reservation.delete", {"id": str(out.id)}, ctx_for(MANAGER))
    assert run("reservation.reservation.delete", {"id": str(out.id)}).id == out.id
    reservation = Reservation.objects.get(pk=out.id)
    assert (reservation.is_deleted, reservation.deleted_at) == (True, NOW)
    assert events()[-2:] == [
        "reservation.reservation.deleted",
        "reservation.reservation.status_changed",
    ]
    assert payload("reservation.reservation.status_changed")["status"] == "deleted"
    with pytest.raises(NotFound):
        run("reservation.reservation.get", {"id": str(out.id)})


def test_the_pending_ones_nobody_confirmed_are_released_after_their_window(monkeypatch):
    stale = make_reservation(date=dt.date(2026, 10, 14), time="11:40")
    on_time = make_reservation(date=dt.date(2026, 10, 14), time="11:50")
    confirmed = make_reservation(
        date=dt.date(2026, 10, 14), time="11:00", status="confirmed"
    )
    yesterday = make_reservation(date=dt.date(2026, 10, 13), time="21:00")
    tomorrow = make_reservation()
    released = run("reservation.reservation.release_unconfirmed", {}, system_context(A))
    assert released.released == 2
    statuses = {
        row.pk: (row.status, row.cancellation_reason)
        for row in Reservation.objects.all()
    }
    assert statuses[stale.pk] == ("cancelled", "unconfirmed")
    assert statuses[yesterday.pk] == ("cancelled", "unconfirmed")
    assert statuses[on_time.pk][0] == statuses[tomorrow.pk][0] == "pending"
    assert statuses[confirmed.pk][0] == "confirmed"
    assert payload("reservation.reservation.unconfirmed_released") == {"count": 2}
    assert (
        run(
            "reservation.reservation.release_unconfirmed", {}, system_context(A)
        ).released
        == 0
    )
    assert events().count("reservation.reservation.unconfirmed_released") == 1


def test_the_window_to_release_is_the_rules_one():
    set_rules(no_show_window_minutes=60)
    make_reservation(date=dt.date(2026, 10, 14), time="11:30")
    assert (
        run(
            "reservation.reservation.release_unconfirmed", {}, system_context(A)
        ).released
        == 0
    )


# ── Slots (F01) and blocked dates (F02) ──────────────────────────────────────────────────────────


def test_a_manager_creates_and_removes_slots_that_do_not_overlap():
    manager = ctx_for(MANAGER)
    lunch = run(
        "reservation.time_slot.create",
        {"day_of_week": 3, "start_time": "13:00", "end_time": "16:00"},
        manager,
    )
    assert (lunch.max_reservations, lunch.max_covers) == (10, None)
    error = refusal(
        lambda: run(
            "reservation.time_slot.create",
            {"day_of_week": 3, "start_time": "15:30", "end_time": "17:00"},
            manager,
        )
    )
    assert (error.code, error.message) == (
        "reservation.slot_overlaps",
        "That slot overlaps another one of the same day (13:00–16:00).",
    )
    assert (
        run(
            "reservation.time_slot.create",
            {
                "day_of_week": 3,
                "start_time": "16:00",
                "end_time": "18:00",
                "max_covers": 30,
            },
            manager,
        ).max_covers
        == 30
    )
    run(
        "reservation.time_slot.delete",
        {"day_of_week": 3, "start_time": "13:00"},
        manager,
    )
    assert TimeSlot.objects.get(pk=lunch.id).is_deleted is True
    assert (
        run(
            "reservation.time_slot.create",
            {"day_of_week": 3, "start_time": "13:00", "end_time": "16:00"},
            manager,
        ).id
        != lunch.id
    )
    assert events() == [
        "reservation.time_slot.created",
        "reservation.time_slot.created",
        "reservation.time_slot.deleted",
        "reservation.time_slot.created",
    ]
    with pytest.raises(PermissionDenied):
        run(
            "reservation.time_slot.create",
            {"day_of_week": 4, "start_time": "13:00", "end_time": "16:00"},
            ctx_for(EMPLOYEE),
        )


def test_a_missing_slot_is_not_found():
    with pytest.raises(NotFound) as caught:
        run("reservation.time_slot.delete", {"day_of_week": 3, "start_time": "13:00"})
    assert caught.value.code == "reservation.slot_not_found"


def test_a_date_is_blocked_whole_or_for_some_hours_once_and_unblocked():
    whole = run(
        "reservation.blocked_date.create", {"date": "2026-10-15", "reason": "Holiday"}
    )
    assert whole.is_full_day is True
    error = refusal(
        lambda: run("reservation.blocked_date.create", {"date": "2026-10-15"})
    )
    assert (error.code, error.message) == (
        "reservation.blocked_date_exists",
        "That date is already blocked at that time.",
    )
    hours = run(
        "reservation.blocked_date.create",
        {
            "date": "2026-10-16",
            "is_full_day": False,
            "blocked_from": "20:00",
            "blocked_until": "22:00",
        },
    )
    assert (hours.blocked_from, hours.blocked_until) == (dt.time(20), dt.time(22))
    run("reservation.blocked_date.delete", {"date": "2026-10-15"})
    assert BlockedDate.objects.get(pk=whole.id).is_deleted is True
    assert events() == [
        "reservation.blocked_date.created",
        "reservation.blocked_date.created",
        "reservation.blocked_date.deleted",
    ]


# ── Waitlist (F14–F16) ───────────────────────────────────────────────────────────────────────────


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


# ── Settings (F03, F04) ──────────────────────────────────────────────────────────────────────────


def test_the_settings_change_only_what_is_sent():
    saved = run(
        "reservation.settings.update",
        {"auto_confirm": True, "max_party_size": 12},
        ctx_for(MANAGER),
    )
    assert (saved.auto_confirm, saved.max_party_size, saved.require_phone) == (
        True,
        12,
        True,
    )
    assert Settings.objects.get().auto_confirm is True
    assert payload("reservation.settings.updated") == {
        "fields": ["auto_confirm", "max_party_size"]
    }
    with pytest.raises(PermissionDenied):
        run("reservation.settings.update", {"auto_confirm": False}, ctx_for(EMPLOYEE))


def test_the_minimum_guests_cannot_pass_the_maximum():
    # A 422 on its field: it is the form's mistake, not a state of the book.
    with pytest.raises(InvalidPayload) as caught:
        run("reservation.settings.update", {"min_party_size": 10, "max_party_size": 4})
    assert caught.value.fields == {"min_party_size": "The minimum guests cannot be more than the maximum."}
    assert not Settings.objects.exists()  # a refusal writes nothing, not even the factory row


# ── Reactions to Customers (F21, F22) ────────────────────────────────────────────────────────────


def test_a_merge_moves_the_absorbed_cards_reservations_and_entries_and_repeats_harmlessly():
    from .conftest import make_customer

    survivor, absorbed, other = (
        make_customer("Ana"),
        make_customer("Ana G."),
        make_customer("Luis"),
    )
    mine = make_reservation(customer_id=absorbed.id, guest_name="Ana G.")
    entry = make_entry(customer_id=absorbed.id)
    theirs = make_reservation(customer_id=other.id)
    data = {"id": str(survivor.id), "absorbed_id": str(absorbed.id)}
    assert run("reservation.customer.reassign", data, system_context(A)).changed == 2
    assert Reservation.objects.get(pk=mine.pk).customer_id == survivor.id
    assert Reservation.objects.get(pk=mine.pk).guest_name == "Ana G."
    assert WaitlistEntry.objects.get(pk=entry.pk).customer_id == survivor.id
    assert Reservation.objects.get(pk=theirs.pk).customer_id == other.id
    assert run("reservation.customer.reassign", data, system_context(A)).changed == 0
    assert events() == ["reservation.customer.reassigned"]


def test_an_erasure_empties_the_personal_data_and_keeps_the_booking():
    from .conftest import make_customer

    card = make_customer("Ana")
    reservation = make_reservation(
        customer_id=card.id,
        guest_phone="+34600111222",
        guest_email="ana@x.es",
        notes="Allergic",
        internal_notes="Wheelchair",
        cancellation_reason="Ill",
        party_size=4,
    )
    entry = make_entry(customer_id=card.id, notes="x", is_deleted=True)
    assert (
        run(
            "reservation.customer.erase", {"id": str(card.id)}, system_context(A)
        ).changed
        == 2
    )
    reservation.refresh_from_db()
    assert (
        reservation.guest_name,
        reservation.guest_phone,
        reservation.guest_email,
        reservation.notes,
        reservation.internal_notes,
        reservation.cancellation_reason,
    ) == ("", "", "", "", "", "")
    assert (reservation.party_size, reservation.customer_id, reservation.date) == (
        4,
        card.id,
        TOMORROW,
    )
    entry.refresh_from_db()
    assert (entry.guest_name, entry.guest_phone, entry.notes) == ("", "", "")
    assert (
        run(
            "reservation.customer.erase", {"id": str(card.id)}, system_context(A)
        ).changed
        == 0
    )
    assert events() == ["reservation.customer.erased"]


def test_the_reactions_are_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run("reservation.customer.erase", {"id": None})
    assert run("reservation.customer.erase", {}, system_context(A)).changed == 0


# ── Review of 2026-10-21: who changes a guest's own booking (F08) and the WhatsApp door (F17, F18) ─────────


def test_the_staff_change_a_booking_the_guest_made_herself_without_her_rules(week):
    # Duda 8: the book's rules bind the guest who books herself, not the staff who change her booking later:
    # 25 guests and tomorrow's dinner full are the staff's call, with «Book anyway?» for the full slot.
    set_rules(max_party_size=20)
    out = book(source="whatsapp", date="2026-10-16")
    changed = run("reservation.reservation.update", {"id": str(out.id), "party_size": 25}, ctx_for(EMPLOYEE))
    assert changed.party_size == 25
    book(time="14:00", guest_name="Eva", guest_phone="600444555")
    for _ in range(9):
        book(time="14:30", guest_name="Luis", guest_phone="600555666")
    error = refusal(
        lambda: run(
            "reservation.reservation.update",
            {"id": str(out.id), "date": "2026-10-15", "time": "14:00", "party_size": 2},
            ctx_for(EMPLOYEE),
        )
    )
    assert (error.code, "overbook" in (error.fields or {})) == ("reservation.no_capacity", True)
    moved = run(
        "reservation.reservation.update",
        {"id": str(out.id), "date": "2026-10-15", "time": "14:00", "party_size": 2, "overbook": True},
        ctx_for(EMPLOYEE),
    )
    assert (moved.date, moved.time) == (TOMORROW, dt.time(14, 0))


def test_a_guest_booking_by_whatsapp_without_a_name_is_booked_under_her_phone():
    # The old module's F17: «si no da ninguno, su teléfono hace de nombre». WhatsApp hands the number in
    # international form.
    open_week()
    out = book(source="whatsapp", guest_name="", guest_phone="+34600999888", date="2026-10-16")
    assert (out.guest_name, out.guest_phone, out.source) == ("+34600999888", "+34600999888", "whatsapp")
    assert run("customer.customer.detail", {"id": str(out.customer_id)}).name == "+34600999888"


def test_a_guest_with_a_card_books_by_whatsapp_under_the_name_she_writes(week):
    first = book(guest_name="Ana García", guest_phone="600111222")
    again = book(source="whatsapp", guest_name="Anita", guest_phone="600111222", date="2026-10-16", time="21:30")
    assert (again.customer_id, again.guest_name) == (first.customer_id, "Anita")


def on_behalf(name: str, data: dict, customer_id):
    """``name`` as a channel acting for the guest herself (WhatsApp), as the system."""
    return run(name, {**data, "on_behalf_of": str(customer_id)}, system_context(A))


def test_a_guest_changes_her_own_booking_through_the_channel_under_her_rules(week):
    out = book(source="whatsapp", date="2026-10-16")
    changed = on_behalf("reservation.reservation.update", {"id": str(out.id), "time": "21:30", "party_size": 3}, out.customer_id)
    assert (changed.time, changed.party_size) == (dt.time(21, 30), 3)
    # Her rules, not the staff's: a group past the limits, or a change too close to now, is refused.
    set_rules(max_party_size=6)
    error = refusal(lambda: on_behalf("reservation.reservation.update", {"id": str(out.id), "party_size": 7}, out.customer_id))
    assert error.code == "reservation.party_size_exceeded"
    phoned = book(guest_name="Ana García", guest_phone="600111222", time="22:00")
    error = refusal(lambda: on_behalf("reservation.reservation.update", {"id": str(phoned.id), "date": "2026-10-14", "time": "12:30"}, phoned.customer_id))
    assert error.code == "reservation.too_soon"


def test_a_guest_cancels_her_own_booking_through_the_channel(week):
    table = make_table("5")
    out = book(source="whatsapp", date="2026-10-16", table_id=str(table.id))
    run("reservation.reservation.confirm", {"id": str(out.id)})
    cancelled = on_behalf("reservation.reservation.cancel", {"id": str(out.id), "reason": "Plans changed"}, out.customer_id)
    assert (cancelled.status, cancelled.cancellation_reason) == ("cancelled", "Plans changed")


@pytest.mark.parametrize("action", ["update", "cancel"])
def test_the_channel_never_touches_a_booking_that_is_not_the_guests(week, action):
    hers, other = book(guest_name="Ana García", guest_phone="600111222"), book(
        guest_name="Bea Ruiz", guest_phone="600333444", time="21:30"
    )
    walk_in = make_reservation(time="22:00")
    gone = make_reservation(time="22:30", customer_id=hers.customer_id, is_deleted=True)
    data = {"party_size": 3} if action == "update" else {}
    before = events()
    for target in (other.id, walk_in.id, gone.id, "01a15d83-0000-7000-8000-000000000000"):
        error = refusal(lambda: on_behalf(f"reservation.reservation.{action}", {"id": str(target), **data}, hers.customer_id))
        assert (error.code, error.message) == (
            "reservation.customer_mismatch",
            "That reservation belongs to a different guest, so it cannot be managed on their behalf.",
        ), target
    assert events() == before
    assert Reservation.objects.get(pk=other.id).party_size == 4
    assert Reservation.objects.get(pk=other.id).status == "pending"


def test_whose_booking_it_is_is_asked_before_its_status(week):
    out = book(guest_name="Bea Ruiz", guest_phone="600333444")
    Reservation.objects.filter(pk=out.id).update(status="completed")
    stranger = book(guest_name="Ana García", guest_phone="600111222", time="21:30")
    error = refusal(lambda: on_behalf("reservation.reservation.cancel", {"id": str(out.id)}, stranger.customer_id))
    assert error.code == "reservation.customer_mismatch"


@pytest.mark.parametrize(
    "sent",
    [{"table": "5"}, {"no_table": True}, {"internal_notes": "VIP"}, {"overbook": True}],
)
def test_the_table_and_the_internal_notes_stay_the_restaurants(week, sent):
    make_table("5")
    out = book(source="whatsapp", date="2026-10-16", internal_notes="Regular")
    error = refusal(lambda: on_behalf("reservation.reservation.update", {"id": str(out.id), **sent}, out.customer_id))
    assert (error.code, error.message) == (
        "reservation.staff_only_field",
        "The table and the restaurant's internal notes are set by the restaurant: they cannot be changed from the "
        "guest's own booking.",
    )
    row = Reservation.objects.get(pk=out.id)
    assert (row.table_id, row.internal_notes) == (None, "Regular")


def test_confirming_a_whatsapp_booking_announces_what_the_whatsapp_notice_reads(week):
    # RESERVATION-F19, Reservations' half: confirming says so in the outbox, and the booking's detail says it came
    # by WhatsApp and from which number, which is what a notice to the guest needs.
    out = book(source="whatsapp", guest_phone="+34600999888", date="2026-10-16")
    run("reservation.reservation.confirm", {"id": str(out.id)}, ctx_for(EMPLOYEE))
    told = payload("reservation.reservation.status_changed")
    assert (told["id"], told["status"], told["previous_status"], told["customer_id"]) == (
        str(out.id),
        "confirmed",
        "pending",
        str(out.customer_id),
    )
    detail = run("reservation.reservation.get", {"id": str(out.id)}, ctx_for(EMPLOYEE))
    assert (detail.source, detail.guest_phone, detail.date, detail.time) == (
        "whatsapp",
        "+34600999888",
        dt.date(2026, 10, 16),
        dt.time(21, 0),
    )
