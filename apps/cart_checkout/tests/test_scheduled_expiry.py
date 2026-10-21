"""CART_CHECKOUT-F07 as the worker runs it: ``cart_checkout.cart.cleanup_expired`` through ``base.scheduler``
every quarter of an hour, as the system on the worker's scope (phase 1: one scope, the carts are shared).
An active cart past its expiry is stored as expired with one event that says how many; a cart without an
expiry, one not yet due, one that is not active or one deleted stays as it was; the next quarter, with
nothing new, expires nothing and says nothing.
"""

import datetime as dt

import pytest
from live.models import OutboxEvent

from apps.cart_checkout import events
from apps.cart_checkout.models import Cart
from base import scheduler

from .conftest import NOW, make_cart

pytestmark = pytest.mark.django_db

TASK = "cart_checkout.expire_overdue_carts"
#: The worker schedules the task at 08:01 UTC; it is due at the next quarter.
STARTED = NOW + dt.timedelta(minutes=1)
DUE = NOW + dt.timedelta(minutes=15)


@pytest.fixture
def worker(settings, monkeypatch, clock):
    """The worker's scope and cart_checkout's task, scheduled as the worker does at 08:01 UTC."""
    settings.WORKER_SCOPE_SLUG = "a"
    # Inside the test's transaction a released connection could not be opened again.
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: None)
    clock.at(STARTED)
    scheduler.sync(STARTED, declared=[task for task in scheduler.tasks() if task.app_label == "cart_checkout"])
    return clock


def expired_events() -> list[dict]:
    return list(OutboxEvent.objects.filter(name=events.CART_EXPIRED).values_list("payload", flat=True))


def status(cart) -> str:
    return Cart.objects.get(pk=cart.pk).status


def test_the_worker_expires_the_overdue_carts_every_quarter_of_an_hour(worker):
    overdue = make_cart("sess_overdue", expires_at=NOW + dt.timedelta(minutes=5))
    also_overdue = make_cart("sess_also", expires_at=NOW - dt.timedelta(days=1))
    not_yet = make_cart("sess_not_yet", expires_at=NOW + dt.timedelta(hours=2))
    never = make_cart("sess_never")
    abandoned = make_cart("sess_abandoned", status=Cart.Status.ABANDONED, expires_at=NOW - dt.timedelta(days=1))
    deleted = make_cart("sess_deleted", expires_at=NOW - dt.timedelta(days=1), deleted_at=NOW)
    assert scheduler.next_after("*/15 * * * *", STARTED) == DUE

    # Not before its quarter of an hour.
    assert scheduler.run_due(DUE - dt.timedelta(seconds=30)) == []
    assert status(overdue) == Cart.Status.ACTIVE

    worker.at(DUE)
    assert scheduler.run_due(DUE) == [TASK]
    assert [status(cart) for cart in (overdue, also_overdue)] == [Cart.Status.EXPIRED, Cart.Status.EXPIRED]
    assert [status(cart) for cart in (not_yet, never, deleted)] == [Cart.Status.ACTIVE] * 3
    assert status(abandoned) == Cart.Status.ABANDONED
    assert expired_events() == [{"count": 2}]

    # The next quarter runs again and, with nothing new, says nothing.
    later = DUE + dt.timedelta(minutes=15)
    worker.at(later)
    assert scheduler.run_due(later) == [TASK]
    assert len(expired_events()) == 1
