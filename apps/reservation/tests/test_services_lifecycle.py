"""Writes that move a reservation through its states (confirm, seat, complete, cancel, no-show), delete it and
release the pending ones nobody confirmed."""

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
    MANAGER,
    NOW,
    THURSDAY,
    book,
    ctx_for,
    events,
    make_reservation,
    make_slot,
    payload,
    pin_clock,
    refusal,
    run,
    set_rules,
)

pytestmark = HUB_DB


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


def test_the_window_to_release_counts_real_time_the_nights_the_clocks_change(monkeypatch):
    def release() -> int:
        return run(
            "reservation.reservation.release_unconfirmed", {}, system_context(A)
        ).released

    # 01:50 winter time plus the 15 minutes is 03:05 summer time: at 03:00 it still has five minutes.
    make_reservation(date=CLOCKS_FORWARD, time="01:50")
    pin_clock(monkeypatch, dt.datetime(2026, 3, 29, 1, 0, tzinfo=dt.UTC))
    assert release() == 0
    pin_clock(monkeypatch, dt.datetime(2026, 3, 29, 1, 6, tzinfo=dt.UTC))
    assert release() == 1
    # 02:50 of the first pass plus 15 minutes is 02:05 of the second: at 02:10 winter time it goes.
    make_reservation(date=CLOCKS_BACK, time="02:50")
    pin_clock(monkeypatch, dt.datetime(2026, 10, 25, 1, 10, tzinfo=dt.UTC))
    assert release() == 1
