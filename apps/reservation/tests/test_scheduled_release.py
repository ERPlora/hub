"""RESERVATION-F13 as the worker runs it: ``reservation.reservation.release_unconfirmed`` through
``base.scheduler`` every quarter of an hour, as the system on the worker's scope (phase 1: one scope, the
bookings are shared). A pending reservation whose time passed more than the window (15 minutes) is cancelled as
«unconfirmed» with one event that says how many; one still inside its window, a confirmed one and one of
tomorrow stay as they were; the next quarter, with nothing new, releases nothing and says nothing.
"""

import datetime as dt

import pytest
from live.models import OutboxEvent

from apps.reservation import events
from apps.reservation.models import Reservation
from base import scheduler

from .conftest import NOW, TODAY, make_reservation, pin_clock

pytestmark = pytest.mark.django_db

TASK = "reservation.release_unconfirmed_reservations"
#: The worker schedules the task at 12:01 in Madrid (10:01 UTC); it is due at the next quarter, 12:15.
STARTED = NOW + dt.timedelta(minutes=1)
DUE = NOW + dt.timedelta(minutes=15)


@pytest.fixture
def worker(settings, monkeypatch):
    """The worker's scope and Reservations' task, scheduled as the worker does at 12:01 in Madrid."""
    settings.WORKER_SCOPE_SLUG = "a"
    # Inside the test's transaction a released connection could not be opened again.
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: None)
    pin_clock(monkeypatch, STARTED)
    scheduler.sync(STARTED, declared=[task for task in scheduler.tasks() if task.app_label == "reservation"])
    return lambda instant: pin_clock(monkeypatch, instant)


def released_events() -> list[dict]:
    return list(
        OutboxEvent.objects.filter(name=events.RESERVATION_UNCONFIRMED_RELEASED).values_list("payload", flat=True)
    )


def state(reservation) -> tuple[str, str]:
    row = Reservation.objects.get(pk=reservation.pk)
    return row.status, row.cancellation_reason


def test_the_worker_releases_the_pending_ones_nobody_confirmed_every_quarter_of_an_hour(worker):
    stale = make_reservation(date=TODAY, time="11:55")
    inside = make_reservation(date=TODAY, time="12:05")
    confirmed = make_reservation(date=TODAY, time="11:00", status="confirmed")
    tomorrow = make_reservation()
    assert scheduler.next_after("*/15 * * * *", STARTED) == DUE

    # Not before its quarter of an hour.
    assert scheduler.run_due(DUE - dt.timedelta(seconds=30)) == []
    assert state(stale) == ("pending", "")

    worker(DUE)
    assert scheduler.run_due(DUE) == [TASK]
    assert state(stale) == ("cancelled", "unconfirmed")
    assert [state(row)[0] for row in (inside, tomorrow)] == ["pending", "pending"]
    assert state(confirmed)[0] == "confirmed"
    assert released_events() == [{"count": 1}]
    event = OutboxEvent.objects.get(name=events.RESERVATION_UNCONFIRMED_RELEASED)
    assert (event.scope_kind, event.scope_key) == ("host", "a")

    # The next quarter releases the one whose window has passed by then, and says so once more.
    later = DUE + dt.timedelta(minutes=15)
    worker(later)
    assert scheduler.run_due(later) == [TASK]
    assert state(inside) == ("cancelled", "unconfirmed")
    assert released_events() == [{"count": 1}, {"count": 1}]

    # With nothing new, the next one says nothing.
    last = later + dt.timedelta(minutes=15)
    worker(last)
    assert scheduler.run_due(last) == [TASK]
    assert len(released_events()) == 2
