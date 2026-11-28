"""Writes of a reservation itself: taking one (``reservation.reservation.create``), changing it
(``reservation.reservation.update``) and who may change a guest's own booking, WhatsApp's door included.

What the table app does with each change (holds, the check opened when seating) is
``test_integration_table.py``; the customer cards, ``test_integration_customer.py``; the opening hours,
``test_integration_schedule.py``.
"""

import datetime as dt

import pytest
from live.context import system_context
from live.errors import NotFound, PermissionDenied

from apps.reservation.models import Reservation

from .conftest import (
    A,
    CLOCKS_BACK,
    CLOCKS_FORWARD,
    EMPLOYEE,
    HUB_DB,
    NOW,
    THURSDAY,
    TOMORROW,
    book,
    ctx_for,
    events,
    make_blocked,
    make_reservation,
    make_slot,
    make_table,
    open_week,
    payload,
    pin_clock,
    refusal,
    run,
    set_rules,
)

pytestmark = HUB_DB

SUNDAY = 6


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


def test_the_table_is_held_for_its_real_time_the_night_the_clocks_go_back():
    make_slot(SUNDAY, "00:00", "05:00")
    five = make_table("5")
    make_reservation(
        date=CLOCKS_BACK, time="01:37", duration_minutes=90, table=five, status="confirmed"
    )
    luis = dict(
        table_id=str(five.id),
        date=CLOCKS_BACK.isoformat(),
        duration_minutes=60,
        guest_name="Luis",
        guest_phone="600333444",
    )
    # 01:37 summer time plus 90 real minutes ends at 02:07 of the second pass: 02:30 (the first) clashes.
    error = refusal(lambda: book(time="02:30", **luis))
    assert (error.code, error.message) == (
        "reservation.table_taken",
        "Table 5 (no zone) already has a reservation from 01:37 to 02:07.",
    )
    assert book(time="03:00", **luis).end_time == dt.time(4, 0)


def test_the_table_is_held_for_its_real_time_the_night_the_clocks_go_forward(monkeypatch):
    pin_clock(monkeypatch, dt.datetime(2026, 3, 20, 11, 0, tzinfo=dt.UTC))
    make_slot(SUNDAY, "00:00", "05:00")
    five = make_table("5")
    make_reservation(
        date=CLOCKS_FORWARD, time="01:00", duration_minutes=90, table=five, status="confirmed"
    )
    luis = dict(
        table_id=str(five.id),
        date=CLOCKS_FORWARD.isoformat(),
        duration_minutes=60,
        guest_name="Luis",
        guest_phone="600333444",
    )
    # 01:00 winter time plus 90 real minutes ends at 03:30 summer time.
    error = refusal(lambda: book(time="03:00", **luis))
    assert (error.code, error.message) == (
        "reservation.table_taken",
        "Table 5 (no zone) already has a reservation from 01:00 to 03:30.",
    )
    assert book(time="03:30", **luis).end_time == dt.time(4, 30)


def test_a_time_gone_is_judged_by_real_time_the_night_the_clocks_go_back(monkeypatch):
    # 02:20 of the second pass (01:20 UTC): the 02:40 a reservation keeps is the first, gone an hour ago.
    pin_clock(monkeypatch, dt.datetime(2026, 10, 25, 1, 20, tzinfo=dt.UTC))
    make_slot(SUNDAY, "00:00", "05:00")
    error = refusal(lambda: book(date=CLOCKS_BACK.isoformat(), time="02:40"))
    assert error.code == "reservation.in_past"
    assert book(date=CLOCKS_BACK.isoformat(), time="03:00").time == dt.time(3, 0)

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


# ── Who changes a guest's own booking (F08) and the WhatsApp door (F17, F18) ─────────────────────


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
        error = refusal(lambda target=target: on_behalf(f"reservation.reservation.{action}", {"id": str(target), **data}, hers.customer_id))
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
