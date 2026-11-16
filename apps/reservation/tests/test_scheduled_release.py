"""RESERVATION-F13 through the scheduler's clock: ``reservation.reservation.release_unconfirmed`` through
``base.scheduler`` every quarter of an hour, as the system, on business A's scope, as the worker's pass over the hubs
runs it on each hub's (that pass itself: ``test_scheduled_release_per_hub.py``). A pending reservation whose time passed more than the window (15 minutes) is cancelled as
«unconfirmed» with one event that says how many; one still inside its window, a confirmed one and one of
tomorrow stay as they were; the next quarter, with nothing new, releases nothing and says nothing. A pending one
of a day already gone is released too: the one at 23:55, whose window ends after midnight, goes at 00:15.
"""

import datetime as dt

import pytest
from live.models import OutboxEvent

from apps.reservation import events
from apps.reservation.models import Reservation
from base import scheduler

from .conftest import HUB_DB, NOW, TODAY, TOMORROW, A, make_reservation, pin_clock

pytestmark = HUB_DB

TASK = "reservation.release_unconfirmed_reservations"
#: The worker schedules the task at 12:01 in Madrid (10:01 UTC); it is due at the next quarter, 12:15.
STARTED = NOW + dt.timedelta(minutes=1)
DUE = NOW + dt.timedelta(minutes=15)


def schedule(monkeypatch, started: dt.datetime):
    """Reservations' task, scheduled as the worker does at ``started``; returns what moves the clock."""
    # Inside the test's transaction a released connection could not be opened again.
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: None)
    pin_clock(monkeypatch, started)
    scheduler.sync(started, declared=[task for task in scheduler.tasks() if task.app_label == "reservation"])
    return lambda instant: pin_clock(monkeypatch, instant)


@pytest.fixture
def worker(monkeypatch):
    """The worker scheduled at 12:01 in Madrid."""
    return schedule(monkeypatch, STARTED)


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
    assert scheduler.run_due(DUE - dt.timedelta(seconds=30), scope=A) == []
    assert state(stale) == ("pending", "")

    worker(DUE)
    assert scheduler.run_due(DUE, scope=A) == [TASK]
    assert state(stale) == ("cancelled", "unconfirmed")
    assert [state(row)[0] for row in (inside, tomorrow)] == ["pending", "pending"]
    assert state(confirmed)[0] == "confirmed"
    assert released_events() == [{"count": 1}]
    event = OutboxEvent.objects.get(name=events.RESERVATION_UNCONFIRMED_RELEASED)
    assert (event.scope_kind, event.scope_key) == ("host", A.key)

    # The next quarter releases the one whose window has passed by then, and says so once more.
    later = DUE + dt.timedelta(minutes=15)
    worker(later)
    assert scheduler.run_due(later, scope=A) == [TASK]
    assert state(inside) == ("cancelled", "unconfirmed")
    assert released_events() == [{"count": 1}, {"count": 1}]

    # With nothing new, the next one says nothing.
    last = later + dt.timedelta(minutes=15)
    worker(last)
    assert scheduler.run_due(last, scope=A) == [TASK]
    assert len(released_events()) == 2


def test_a_pending_one_of_a_day_already_gone_is_released_too(monkeypatch):
    # 23:55 plus the 15 minutes is 00:10 of the next day: by then its day is yesterday's, and it goes all the same.
    late = make_reservation(date=TODAY, time="23:55")
    next_night = make_reservation(date=TOMORROW, time="23:55")
    # The worker schedules the task at 23:46 in Madrid (21:46 UTC); midnight there is 22:00 UTC.
    midnight = dt.datetime(2026, 10, 14, 22, 0, tzinfo=dt.UTC)
    worker = schedule(monkeypatch, midnight - dt.timedelta(minutes=14))

    worker(midnight)
    assert scheduler.run_due(midnight, scope=A) == [TASK]
    assert state(late) == ("pending", "")

    quarter_past = midnight + dt.timedelta(minutes=15)
    worker(quarter_past)
    assert scheduler.run_due(quarter_past, scope=A) == [TASK]
    assert state(late) == ("cancelled", "unconfirmed")
    assert state(next_night) == ("pending", "")
    assert released_events() == [{"count": 1}]
