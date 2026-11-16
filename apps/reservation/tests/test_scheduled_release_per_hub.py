"""RESERVATION-F13 in hubs with a database of their own (hub#551): the worker's pass over the hubs
(``base.worker._hubs``) runs the release in each hub's database and on that hub's scope, so the Reservations screen of
the business whose pending reservation was released hears it at once (its live notice on its channel, the one its
open list listens on) and the screen of another business hears nothing; nor does the worker's fixed scope
(``WORKER_SCOPE_SLUG``, the platform hub in production).

Two real databases (the session's ``hub_a`` and ``hub_b``), committed (``transaction=True``). The notices are heard as a
live stream hears them: ``LISTEN`` on the scope's channel, in control.
"""

import datetime as dt
import json

import psycopg
import pytest
from django.conf import settings
from django.db import connections
from live.live_registry import live_registry
from live.context import Scope
from live.outbox import channel_for
from psycopg.conninfo import make_conninfo

from apps.reservation import events
from apps.reservation.models import Reservation
from base import worker
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from control.models import Hub

from .conftest import NOW, TODAY, TOMORROW, make_reservation, pin_clock

pytestmark = [
    pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback", "nothing_served_yet"),
]

#: The worker's first pass writes each hub's schedule at 12:01 in Madrid; the release is due at the next quarter.
STARTED = NOW + dt.timedelta(minutes=1)
DUE = NOW + dt.timedelta(minutes=15)
NEXT_QUARTER = DUE + dt.timedelta(minutes=15)
#: Last night's booking: past its window whatever the business's zone.
YESTERDAY = TODAY - dt.timedelta(days=1)
#: The live query the Reservations screen keeps open on the day it shows.
SCREEN = "reservation.reservation.list"


@pytest.fixture
def no_test_fallback(monkeypatch):
    from base.tenancy import context

    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.fixture
def nothing_served_yet(monkeypatch):
    monkeypatch.setattr(worker, "_synced", set())
    monkeypatch.setattr(worker, "_next_hub", None)


@pytest.fixture
def listen(django_db_setup):
    """A raw session in control listening on a scope's channel, as a live stream does."""
    params = connections["default"].settings_dict
    dsn = make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )
    sessions = []

    def open_session(slug: str):
        session = psycopg.connect(dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(Scope('host', slug))}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def released_notices(session, timeout: float = 0.5) -> int:
    """How many notices heard on ``session`` say pending reservations were released."""
    return sum(
        events.RESERVATION_UNCONFIRMED_RELEASED in json.loads(note.payload).get("events", [])
        for note in session.notifies(timeout=timeout)
    )


def state_in(hub, reservation) -> tuple[str, str]:
    with use_hub(Hub.objects.get(pk=hub.pk)):
        row = Reservation.objects.get(pk=reservation.pk)
        return row.status, row.cancellation_reason


def pass_at(monkeypatch, instant: dt.datetime) -> None:
    """One tick of the worker over the hubs, at ``instant``."""
    pin_clock(monkeypatch, instant)
    with use_control():
        worker._hubs(instant)


def test_a_release_by_the_worker_is_heard_by_its_business_and_by_no_other(hub_a, hub_b, listen, monkeypatch):
    assert SCREEN in live_registry.affected([events.RESERVATION_UNCONFIRMED_RELEASED])
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        stale_in_a = make_reservation(date=YESTERDAY, time="21:00")
    with use_hub(Hub.objects.get(pk=hub_b.pk)):
        tonight_in_b = make_reservation(date=TOMORROW, time="21:00")
    on_a, on_b, on_worker = listen(hub_a.slug), listen(hub_b.slug), listen(settings.WORKER_SCOPE_SLUG)
    pass_at(monkeypatch, STARTED)

    # The quarter comes: A's pending booking nobody confirmed is released, and A's open screen is told at once.
    pass_at(monkeypatch, DUE)
    assert state_in(hub_a, stale_in_a) == ("cancelled", "unconfirmed")
    assert state_in(hub_b, tonight_in_b) == ("pending", "")
    assert released_notices(on_a) == 1
    assert released_notices(on_b) == 0
    assert released_notices(on_worker) == 0

    # The other way round: B's booking, now past, is released at the next quarter; B hears it, A does not.
    with use_hub(Hub.objects.get(pk=hub_b.pk)):
        stale_in_b = make_reservation(date=YESTERDAY, time="20:00")
    pass_at(monkeypatch, NEXT_QUARTER)
    assert state_in(hub_b, stale_in_b) == ("cancelled", "unconfirmed")
    assert state_in(hub_b, tonight_in_b) == ("pending", "")
    assert released_notices(on_b) == 1
    assert released_notices(on_a) == 0
    assert released_notices(on_worker) == 0
