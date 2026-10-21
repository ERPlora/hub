"""Reservations hears Customers through the worker's outbox relay, end to end (RESERVATION-F21, F22).

Customers' real operations merge two cards or erase one and record ``customer.customer.merged`` /
``customer.customer.erased`` in the outbox; one tick of the worker's real loop (``base.worker.run`` →
``base.relay``) hands them to Reservations, whose reaction moves the absorbed card's reservations and waitlist
entries to the card that stays, or empties the personal data of the erased card's — once: a second tick, or the
same notice handed over again, changes nothing. An erasure in hub B is heard in B only.
"""

import json
import threading

import psycopg
import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent
from live.outbox import channel_for

from apps.reservation.models import Reservation, WaitlistEntry
from apps.table.models import Hold
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

from .conftest import A, B, TOMORROW, book, ctx_for, holds, make_table, open_week, run

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def one_tick() -> None:
    """One tick of the worker's real loop."""
    stop = threading.Event()

    def wait(_seconds: float) -> bool:
        stop.set()
        return True

    now = timezone.now()
    assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now) == 0


@pytest.fixture
def tick(db, monkeypatch):
    """``one_tick`` without the SaaS (``register_apps``) and, inside the test's transaction, without releasing
    the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)
    return one_tick


def delivery_to_reservation(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to Reservations."""
    event = OutboxEvent.objects.filter(name=name).latest("id")
    row = EventDelivery.objects.get(event_id=event.id, app_label="reservation")
    return row.status, row.attempts


def wait_for(name: str, phone: str, scope=A):
    return run(
        "reservation.waitlist.create",
        {"guest_name": name, "guest_phone": phone, "date": TOMORROW.isoformat(), "preferred_time": "21:00",
         "party_size": 2, "notes": "Window, please"},
        ctx_for(scope=scope),
    )


@pytest.fixture
def week(db):
    open_week()


def test_two_cards_merged_in_customers_take_their_reservations_with_them_through_the_relay(tick, week):
    stays = book(guest_name="Ana García", guest_phone="600111222")
    goes = book(guest_name="Ana G.", guest_phone="600333444", time="21:30")
    entry = wait_for("Ana G.", "600333444")
    survivor, absorbed = stays.customer_id, goes.customer_id
    assert survivor != absorbed

    run("customer.customer.merge", {"id": str(survivor), "absorbed_id": str(absorbed)})
    # Customers' command only records its event: the book waits for the relay.
    assert Reservation.objects.get(pk=goes.id).customer_id == absorbed

    tick()

    assert delivery_to_reservation("customer.customer.merged") == ("delivered", 1)
    assert Reservation.objects.get(pk=goes.id).customer_id == survivor
    assert WaitlistEntry.objects.get(pk=entry.id).customer_id == survivor
    # The name it was booked with does not change.
    assert Reservation.objects.get(pk=goes.id).guest_name == "Ana G."
    reassigned = OutboxEvent.objects.filter(name="reservation.customer.reassigned")
    assert [event.payload for event in reassigned] == [{"id": str(survivor), "absorbed_id": str(absorbed)}]


def test_a_card_erased_in_customers_leaves_its_bookings_without_personal_data_through_the_relay(tick, week):
    table = make_table("5")
    erased = book(guest_name="Ana García", guest_phone="600111222", table_id=str(table.id), notes="Allergic")
    run("reservation.reservation.confirm", {"id": str(erased.id)})
    entry = wait_for("Ana García", "600111222")
    other = book(guest_name="Bea Ruiz", guest_phone="600333444", time="21:30")

    run("customer.customer.erase", {"id": str(erased.customer_id), "reason": "GDPR request"})
    assert Reservation.objects.get(pk=erased.id).guest_name == "Ana García"

    tick()

    assert delivery_to_reservation("customer.customer.erased") == ("delivered", 1)
    gone = Reservation.objects.get(pk=erased.id)
    assert (gone.guest_name, gone.guest_phone, gone.guest_email, gone.notes) == ("", "", "", "")
    # The booking itself stays: day, time, guests, table and status.
    assert (gone.date, gone.party_size, gone.table_id, gone.status) == (TOMORROW, 4, table.id, "confirmed")
    waiting = WaitlistEntry.objects.get(pk=entry.id)
    assert (waiting.guest_name, waiting.guest_phone, waiting.notes) == ("", "", "")
    assert Reservation.objects.get(pk=other.id).guest_name == "Bea Ruiz"
    # The names her reservations announced are gone from the outbox too, and Tables forgot its hold's label
    # by its own reaction to the same notice (TABLE-F31).
    announced = OutboxEvent.objects.filter(name="reservation.reservation.status_changed", payload__id=str(erased.id))
    assert {event.payload["guest_name"] for event in announced} == {""}
    [hold] = holds(erased.id)
    assert (hold.status, hold.label) == (Hold.Status.HELD, "")
    assert [event.payload for event in OutboxEvent.objects.filter(name="reservation.customer.erased")] == [
        {"id": str(erased.customer_id)}
    ]


def test_a_second_tick_or_the_same_notice_handed_over_again_changes_nothing(tick, week):
    erased = book()
    run("customer.customer.erase", {"id": str(erased.customer_id)})
    tick()
    notices = OutboxEvent.objects.filter(name="reservation.customer.erased").count()

    tick()
    assert delivery_to_reservation("customer.customer.erased") == ("delivered", 1)

    # The same notice handed to Reservations again, as if its delivery had been lost: the relay runs it once more.
    event = OutboxEvent.objects.filter(name="customer.customer.erased").latest("id")
    EventDelivery.objects.filter(event_id=event.id, app_label="reservation").update(
        status=EventDelivery.Status.PENDING, delivered_at=None, next_attempt_at=timezone.now()
    )
    tick()

    assert delivery_to_reservation("customer.customer.erased") == ("delivered", 2)
    assert OutboxEvent.objects.filter(name="reservation.customer.erased").count() == notices == 1


# ── Two hubs, on committed data ──────────────────────────────────────────────────────────────


@pytest.fixture
def listen(transactional_db, db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 0.5) -> set[str]:
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


def test_an_erasure_in_hub_b_is_heard_in_b_only(listen, monkeypatch):
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    open_week()
    on_a, on_b = listen(A), listen(B)
    in_b = book(ctx_for(scope=B), guest_name="Bea Ruiz", guest_phone="600333444")
    heard(on_a), heard(on_b)  # the booking's own notices

    run("customer.customer.erase", {"id": str(in_b.customer_id)}, ctx_for(scope=B))
    heard(on_b)  # the erasure's own notice
    one_tick()

    assert Reservation.objects.get(pk=in_b.id).guest_name == ""
    assert "reservation.customer.erased" in heard(on_b)
    assert heard(on_a) == set()
    reaction = OutboxEvent.objects.get(name="reservation.customer.erased")
    assert (reaction.scope_kind, reaction.scope_key) == (B.kind, B.key)
