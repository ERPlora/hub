"""Write operations of the appointment app (one appointment at a time, blocks, settings and the platform's
reactions): what each one writes, what it refuses, and that a refusal leaves no trace.

Cases from the current product's tests (`create_overlap`, `cancel`, `reschedule*`, `history_trail`,
`appointment_update_details`, `appointment_phone_e164`, `command_chains`, `auto_confirm`, `settings*`,
`sale_conversion`, `customer_merge`, `customer_erasure`) and its WORKFLOW; the market decisions of the
WORKBOOK («Cambios frente al producto actual») where they differ.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.appointment.models import Appointment, BlockedTime, Counter, History, Settings

from .conftest import (
    MONDAY,
    assign,
    at,
    ctx_for,
    make_appointment,
    make_customer,
    make_day,
    make_service,
    make_settings,
    make_shift,
    run,
    wall,
)

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("anytime")]


def book(salon, start="10:00", day=MONDAY, **extra):
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(salon.ana.id),
        "start": wall(day, start),
        **extra,
    }
    return run("appointment.appointment.create", data)


def events(name: str) -> list[dict]:
    return [
        event.payload for event in OutboxEvent.objects.filter(name=name).order_by("id")
    ]


def actions(appointment_id) -> list[str]:
    return list(
        History.objects.filter(appointment_id=appointment_id)
        .order_by("at", "id")
        .values_list("action", flat=True)
    )


def refused(code: str, call, error=Conflict):
    before = (
        Appointment.objects.count(),
        History.objects.count(),
        OutboxEvent.objects.count(),
    )
    with pytest.raises(error) as caught:
        call()
    assert caught.value.code == code
    assert (
        Appointment.objects.count(),
        History.objects.count(),
        OutboxEvent.objects.count(),
    ) == before
    return caught.value


# ── Booking (APPOINTMENT-F01) ─────────────────────────────────────────────────────────────────


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


def test_a_time_the_clock_change_skips_is_a_422_on_the_start(salon):
    spring = dt.date(2027, 3, 28)
    make_settings(max_advance_booking=0)
    error = refused(
        "appointment.invalid_local_time",
        lambda: book(salon, "02:30", day=spring),
        InvalidPayload,
    )
    assert "start" in error.fields


def test_an_employee_books_for_themselves_only(salon, make_user):
    user = make_user("bea", role="hub_employee")
    salon.bea.user = user
    salon.bea.save()
    ctx = ctx_for("hub_employee", actor=user)
    from live.operations import get

    op = get("appointment.appointment.create")
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "start": wall(MONDAY, "10:00"),
    }
    own = op(ctx, op.input.model_validate({**data, "staff_id": str(salon.bea.id)}))
    assert own.staff_id == salon.bea.id
    with pytest.raises(PermissionDenied):
        op(ctx, op.input.model_validate({**data, "staff_id": str(salon.ana.id)}))


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


# ── Moving and editing (F04, F06, F22) ────────────────────────────────────────────────────────


def test_moving_keeps_the_number_and_writes_the_change(salon):
    out = book(salon, "10:00")
    moved = run(
        "appointment.appointment.reschedule",
        {"number": out.number, "start": wall(MONDAY, "10:15")},
    )
    assert (moved.number, moved.start) == (out.number, at(MONDAY, "10:15"))
    line = History.objects.filter(appointment_id=out.id, action="rescheduled").get()
    assert line.new_value["start"].startswith(f"{MONDAY.isoformat()}T10:15")
    assert len(events("appointment.appointment.rescheduled")) == 1


def test_handing_over_keeps_the_price_and_changing_services_brings_the_catalogs(salon):
    assign(salon.cut, salon.bea, price=9000)
    assign(salon.cut, salon.ana)
    out = book(salon, "10:00", staff_id=str(salon.bea.id))
    assert out.total == 9000
    handed = run(
        "appointment.appointment.reschedule", {"id": str(out.id), "staff": "Ana"}
    )
    assert (handed.staff_name, handed.total) == ("Ana López", 9000)
    changed = run(
        "appointment.appointment.reschedule",
        {"id": str(out.id), "services": [{"service": "Colour"}]},
    )
    assert (changed.service_names, changed.total, changed.duration_minutes) == (
        "Colour",
        4500,
        60,
    )
    assert actions(out.id) == ["created", "staff_changed", "service_changed"]


def test_only_a_pending_or_confirmed_uncharged_appointment_moves(salon):
    for status in ("in_progress", "completed", "cancelled", "no_show"):
        item = make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status=status
        )
        refused(
            "appointment.cannot_reschedule",
            lambda: run(
                "appointment.appointment.reschedule",
                {"id": str(item.id), "start": wall(MONDAY, "15:00")},
            ),
        )
    charged = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), sale_id=uuid.uuid7()
    )
    refused(
        "appointment.cannot_reschedule",
        lambda: run(
            "appointment.appointment.reschedule",
            {"id": str(charged.id), "start": wall(MONDAY, "15:00")},
        ),
    )


def test_the_customer_moves_only_her_own_appointment_and_keeps_the_notice(salon):
    out = book(salon, "10:00")
    other = make_customer("Pepa Gil", phone="+34600222333")
    refused(
        "appointment.appointment_not_found",
        lambda: run(
            "appointment.appointment.reschedule",
            {
                "id": str(out.id),
                "start": wall(MONDAY, "12:00"),
                "on_behalf_of_customer": True,
                "customer_id": str(other.id),
            },
        ),
        NotFound,
    )
    moved = run(
        "appointment.appointment.reschedule",
        {
            "id": str(out.id),
            "start": wall(MONDAY, "12:00"),
            "on_behalf_of_customer": True,
            "customer": "+34600111222",
            "reason": "Work",
        },
    )
    assert moved.start == at(MONDAY, "12:00")
    line = History.objects.get(appointment_id=out.id, action="rescheduled")
    # Marked as the customer's, and who in the team wrote it down stays.
    assert (line.by_customer, line.reason, line.actor) == (True, "Work", "tester")


def test_on_the_customers_behalf_an_employee_still_changes_only_her_own_agenda(salon, make_user):
    from live.operations import get

    user = make_user("bea", role="hub_employee")
    salon.bea.user = user
    salon.bea.save()
    assign(salon.cut, salon.bea)
    assign(salon.cut, salon.ana)
    own = run(
        "appointment.appointment.create",
        {"customer_id": str(salon.lucia.id), "services": [{"service_id": str(salon.cut.id)}], "staff_id": str(salon.bea.id), "start": wall(MONDAY, "10:00")},
    )
    move = get("appointment.appointment.reschedule")
    asked = {"id": str(own.id), "on_behalf_of_customer": True, "customer_id": str(salon.lucia.id)}
    with pytest.raises(PermissionDenied):
        move(ctx_for("hub_employee", actor=user), move.input.model_validate({**asked, "staff_id": str(salon.ana.id)}))
    assert Appointment.objects.get(pk=own.id).staff_id == salon.bea.id
    moved = move(ctx_for("hub_employee", actor=user), move.input.model_validate({**asked, "start": wall(MONDAY, "11:00")}))
    assert moved.start == at(MONDAY, "11:00")
    assert History.objects.get(appointment_id=own.id, action="rescheduled").actor == "bea"


def test_editing_notes_or_contact_writes_only_that(salon):
    out = book(salon)
    edited = run(
        "appointment.appointment.update",
        {"id": str(out.id), "notes": "Bring photo", "customer_phone": "600 999 888"},
    )
    assert (edited.notes, edited.customer_phone, edited.start) == (
        "Bring photo",
        "+34600999888",
        out.start,
    )
    assert actions(out.id) == ["created"]
    assert len(events("appointment.appointment.updated")) == 1
    error = refused(
        "appointment.phone_invalid",
        lambda: run(
            "appointment.appointment.update",
            {"id": str(out.id), "customer_phone": "12"},
        ),
        InvalidPayload,
    )
    assert "customer_phone" in error.fields
    moved = run(
        "appointment.appointment.update",
        {"id": str(out.id), "start": wall(MONDAY, "12:00"), "internal_notes": "x"},
    )
    assert (moved.start, moved.internal_notes) == (at(MONDAY, "12:00"), "x")
    assert actions(out.id)[-1] == "rescheduled"


# ── States (F03, F05, F07, F08, F09) ──────────────────────────────────────────────────────────


def test_the_state_machine(salon):
    pending = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status="pending"
    )
    assert (
        run("appointment.appointment.confirm", {"id": str(pending.id)}).status
        == "confirmed"
    )
    refused(
        "appointment.cannot_confirm",
        lambda: run("appointment.appointment.confirm", {"id": str(pending.id)}),
    )
    other = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status="pending"
    )
    refused(
        "appointment.cannot_complete",
        lambda: run("appointment.appointment.complete", {"id": str(other.id)}),
    )
    assert (
        run("appointment.appointment.start", {"id": str(pending.id)}).status
        == "in_progress"
    )
    refused(
        "appointment.cannot_start",
        lambda: run("appointment.appointment.start", {"id": str(pending.id)}),
    )
    assert (
        run("appointment.appointment.complete", {"id": str(pending.id)}).status
        == "completed"
    )
    assert actions(pending.id) == ["confirmed", "started", "completed"]
    assert [
        len(events(f"appointment.appointment.{e}"))
        for e in ("confirmed", "started", "completed")
    ] == [1, 1, 1]
    # A pending one may be started at once (the customer is sitting there).
    walk_in = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), status="pending"
    )
    assert (
        run("appointment.appointment.start", {"id": str(walk_in.id)}).status
        == "in_progress"
    )


def test_a_no_show_is_marked_only_once_its_time_has_passed(salon):
    future = book(salon)
    refused(
        "appointment.no_show_too_early",
        lambda: run("appointment.appointment.mark_no_show", {"id": str(future.id)}),
    )
    past = make_appointment(
        salon.lucia, salon.ana, [salon.cut], timezone.now() - dt.timedelta(hours=1)
    )
    assert (
        run("appointment.appointment.mark_no_show", {"id": str(past.id)}).status
        == "no_show"
    )
    assert (
        actions(past.id) == ["no_show"]
        and len(events("appointment.appointment.marked_no_show")) == 1
    )
    refused(
        "appointment.cannot_mark_no_show",
        lambda: run("appointment.appointment.mark_no_show", {"id": str(past.id)}),
    )


def test_cancelling_keeps_the_reason_and_frees_the_time(salon):
    make_settings(allow_overlapping=False)
    out = book(salon)
    cancelled = run(
        "appointment.appointment.cancel", {"id": str(out.id), "reason": "Ill"}
    )
    assert (
        cancelled.status,
        cancelled.cancellation_reason,
        cancelled.cancelled_by_customer,
    ) == ("cancelled", "Ill", False)
    assert cancelled.cancelled_at is not None
    assert (
        History.objects.get(appointment_id=out.id, action="cancelled").reason == "Ill"
    )
    assert book(salon).status == "confirmed"  # the time is free again
    refused(
        "appointment.cannot_cancel",
        lambda: run("appointment.appointment.cancel", {"id": str(out.id)}),
    )
    for status in ("in_progress", "completed"):
        item = make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), status=status
        )
        refused(
            "appointment.cannot_cancel",
            lambda: run("appointment.appointment.cancel", {"id": str(item.id)}),
        )
    charged = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), sale_id=uuid.uuid7()
    )
    refused(
        "appointment.cannot_cancel",
        lambda: run("appointment.appointment.cancel", {"id": str(charged.id)}),
    )


def test_the_customer_cancels_within_the_policy(salon):
    out = book(salon)
    mine = {
        "id": str(out.id),
        "on_behalf_of_customer": True,
        "customer_id": str(salon.lucia.id),
        "reason": "Ill",
    }
    make_settings(allow_customer_cancellation=False)
    refused(
        "appointment.customer_cancellation_disabled",
        lambda: run("appointment.appointment.cancel", mine),
    )
    make_settings(cancellation_notice_hours=24 * 60)
    refused(
        "appointment.cancellation_notice_required",
        lambda: run("appointment.appointment.cancel", mine),
    )
    make_settings()
    other = make_customer("Pepa Gil", phone="+34600222333")
    refused(
        "appointment.appointment_not_found",
        lambda: run(
            "appointment.appointment.cancel", {**mine, "customer_id": str(other.id)}
        ),
        NotFound,
    )
    assert run("appointment.appointment.cancel", mine).cancelled_by_customer is True
    assert (
        History.objects.get(appointment_id=out.id, action="cancelled").by_customer
        is True
    )


# ── Deleting (F11) ────────────────────────────────────────────────────────────────────────────


def test_deleting_archives_and_refuses_what_happened_or_was_charged(salon):
    out = book(salon)
    assert run("appointment.appointment.delete", {"id": str(out.id)}).id == out.id
    assert Appointment.objects.get(pk=out.id).deleted_at is not None
    assert run("appointment.appointment.list", {"date_from": MONDAY}).total == 0
    assert len(events("appointment.appointment.deleted")) == 1
    for fields in (
        {"status": "completed"},
        {"status": "in_progress"},
        {"sale_id": uuid.uuid7()},
    ):
        item = make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), **fields
        )
        refused(
            "appointment.cannot_delete",
            lambda: run("appointment.appointment.delete", {"id": str(item.id)}),
        )


def test_a_bulk_delete_deletes_all_or_none(salon):
    one, two = book(salon, "10:00"), book(salon, "11:00")
    done = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "15:00"), status="completed"
    )
    refused(
        "appointment.cannot_delete",
        lambda: run(
            "appointment.appointment.bulk_delete", {"ids": [str(one.id), str(done.id)]}
        ),
    )
    out = run(
        "appointment.appointment.bulk_delete", {"ids": [str(one.id), str(two.id)]}
    )
    assert set(out.deleted) == {one.id, two.id}


def test_a_manager_does_not_delete():
    with pytest.raises(PermissionDenied):
        run(
            "appointment.appointment.delete",
            {"id": str(uuid.uuid7())},
            role="hub_manager",
        )


# ── Charging (F17): the refusals; the till itself in test_integration_sale.py ──────────────────


def test_only_a_live_uncharged_appointment_with_taxed_services_is_charged(salon):
    cancelled = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "09:00"), status="cancelled"
    )
    refused(
        "appointment.cannot_charge",
        lambda: run("appointment.appointment.charge", {"id": str(cancelled.id)}),
    )
    charged = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), sale_id=uuid.uuid7()
    )
    refused(
        "appointment.already_charged",
        lambda: run("appointment.appointment.charge", {"id": str(charged.id)}),
    )
    untaxed = make_service("Fringe", tax=None)
    item = make_appointment(salon.lucia, salon.ana, [untaxed], at(MONDAY, "11:00"))
    error = refused(
        "appointment.service_needs_tax_setup",
        lambda: run("appointment.appointment.charge", {"id": str(item.id)}),
    )
    assert "Fringe" in error.message


# ── Blocks (F16) ──────────────────────────────────────────────────────────────────────────────


def test_a_block_is_created_for_the_business_or_one_professional_and_removed(salon):
    block = run(
        "appointment.blocked_time.create",
        {
            "title": "Training",
            "start": wall(MONDAY, "12:00"),
            "end": wall(MONDAY, "13:00"),
            "staff": "Ana",
        },
    )
    assert (block.staff_id, block.start) == (salon.ana.id, at(MONDAY, "12:00"))
    refused("appointment.blocked", lambda: book(salon, "12:30"))
    holiday = run(
        "appointment.blocked_time.create",
        {
            "title": "Holiday",
            "block_type": "holiday",
            "start": wall(MONDAY, "15:00"),
            "end": wall(MONDAY, "15:00"),
            "all_day": True,
        },
    )
    assert (holiday.start, holiday.end) == (
        at(MONDAY, "00:00"),
        at(MONDAY + dt.timedelta(days=1), "00:00"),
    )
    assert len(events("appointment.blocked_time.created")) == 2
    run("appointment.blocked_time.delete", {"id": str(block.id)})
    assert not BlockedTime.objects.filter(pk=block.id).exists()
    assert len(events("appointment.blocked_time.deleted")) == 1


def test_an_employee_does_not_block_time():
    with pytest.raises(PermissionDenied):
        run(
            "appointment.blocked_time.create",
            {
                "title": "x",
                "start": wall(MONDAY, "12:00"),
                "end": wall(MONDAY, "13:00"),
            },
            role="hub_employee",
        )


# ── Settings (F19) ────────────────────────────────────────────────────────────────────────────


def test_the_settings_save_only_what_is_sent_and_tell_only_a_change():
    out = run("appointment.settings.update", {"slot_interval": 30})
    assert (out.slot_interval, out.default_duration) == (30, 60)
    assert (
        Settings.objects.count() == 1
        and len(events("appointment.settings.updated")) == 1
    )
    run("appointment.settings.update", {"slot_interval": 30})
    assert len(events("appointment.settings.updated")) == 1
    run("appointment.settings.update", {"calendar_start_hour": 9})
    error = refused(
        "invalid_payload",
        lambda: run("appointment.settings.update", {"calendar_end_hour": 9}),
        InvalidPayload,
    )
    assert "calendar_end_hour" in error.fields
    with pytest.raises(PermissionDenied):
        run("appointment.settings.update", {"slot_interval": 15}, role="hub_manager")


# ── Reactions (run by the platform; the events themselves in test_events.py) ─────────────────


def system(name: str, data: dict):
    """Runs ``name`` as the platform (the outbox relay's reactions)."""
    from live.context import system_context
    from live.operations import get

    from .conftest import A

    op = get(name)
    return op(system_context(A), op.input.model_validate(data))


def test_a_sale_from_an_appointment_marks_it_charged_and_completes_it_once(salon):
    out = book(salon)
    sale = uuid.uuid7()
    payload = {"sale_id": str(sale), "appointment_id": str(out.id)}
    assert system("appointment.appointment.mark_charged", payload).changed == 1
    item = run("appointment.appointment.get", {"id": str(out.id)})
    assert (item.sale_id, item.status, item.charged_at is not None) == (
        sale,
        "completed",
        True,
    )
    assert system("appointment.appointment.mark_charged", payload).changed == 0
    assert actions(out.id) == ["created", "charged", "completed"]
    assert (
        system("appointment.appointment.unmark_charged", {"sale_id": str(sale)}).changed
        == 1
    )
    item = run("appointment.appointment.get", {"id": str(out.id)})
    assert (item.sale_id, item.status) == (None, "completed")
    assert actions(out.id)[-1] == "uncharged"


def test_the_reactions_are_the_platforms_alone(salon):
    with pytest.raises(PermissionDenied):
        run(
            "appointment.appointment.mark_charged",
            {"sale_id": str(uuid.uuid7()), "appointment_id": str(uuid.uuid7())},
        )
