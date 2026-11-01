"""The worker relays the outbox and runs the scheduled tasks of every hub with its own database (review of hub#471, C1).

A hub with its own database records its events (``live.OutboxEvent``) and keeps its schedule (``base.TaskSchedule``) in
that database: the pass over phase 1's shared database never sees them. Every tick, after that pass, the worker enters
each ready hub with its own database (``use_hub``), relays its outbox, writes its apps' schedule once per process and
runs the tasks due in it, as the system on that hub's own scope (``host``, its slug: their live notices go on its
channel, not the platform's; ``FIX-SCHEDULED-TASK-LIVE-NOTICE-WRONG-CHANNEL``), within a time budget per tick and one
hub's connection at a time. A hub still being prepared is never entered.

Real databases: the session's two hubs (``hub_a``, ``hub_b``; ``base/tenancy/tests/hubs.py``), committed
(``transaction=True``: the relay releases its connections between steps).
"""

import datetime as dt

import pytest
from django.db import connections
from django.utils import timezone
from live.models import OutboxEvent

from base import scheduler, worker
from base.models import EventDelivery, TaskSchedule
from base.tenancy.context import current, use_control, use_hub
from base.tenancy.tests import hubs
from control.models import Hub

pytestmark = [
    pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES),
    pytest.mark.usefixtures("no_test_fallback"),
]

EVENT = "demo.item.created"


@pytest.fixture
def no_test_fallback(monkeypatch):
    from base.tenancy import context

    monkeypatch.setattr(context, "_test_fallback", None)


@pytest.fixture(autouse=True)
def nothing_synced_yet(monkeypatch):
    monkeypatch.setattr(worker, "_synced", set())
    monkeypatch.setattr(worker, "_next_hub", None)


def record(hub: Hub, slug: str) -> OutboxEvent:
    with use_hub(hub):
        return OutboxEvent.objects.create(scope_kind="host", scope_key=slug, name=EVENT, payload={"id": "1"})


def test_a_hubs_own_outbox_is_relayed_in_its_own_database_and_a_hub_being_prepared_is_not_entered(hub_a, hub_b):
    Hub.objects.filter(pk=hub_b.pk).update(status=Hub.Status.REQUESTED)
    in_a = record(hub_a, hub_a.slug)
    in_b = record(hub_b, hub_b.slug)

    with use_control():
        worker._hubs(timezone.now())

    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        taken = OutboxEvent.objects.get(pk=in_a.pk)
        deliveries = set(EventDelivery.objects.filter(event=taken).values_list("app_label", flat=True))
    with use_hub(Hub.objects.get(pk=hub_b.pk)):
        untouched = OutboxEvent.objects.get(pk=in_b.pk)
    assert taken.delivered_at is not None and "flow" in deliveries
    assert untouched.delivered_at is None


def test_a_hubs_tasks_are_scheduled_in_its_database_and_run_on_its_own_scope(hub_a, monkeypatch):
    ran = []
    monkeypatch.setattr(
        scheduler, "_execute", lambda name, scope=None: ran.append((name, scope.key, current().alias))
    )
    now = timezone.now()

    with use_control():
        worker._hubs(now)
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        scheduled = TaskSchedule.objects.count()
    assert scheduled == len(scheduler.tasks()) and ran == []  # written once, due at their next time

    with use_control():
        worker._hubs(now + dt.timedelta(days=2))

    alias = f"hub_{hub_a.id.hex}"
    assert ran and {(scope, where) for _name, scope, where in ran} == {(hub_a.slug, alias)}


def test_a_task_of_an_app_the_hub_has_off_is_not_run(hub_a, monkeypatch):
    from base.models import AppActivation

    ran = []
    monkeypatch.setattr(scheduler, "_execute", lambda name, scope=None: ran.append(name))
    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        AppActivation.objects.filter(host=hub_a.slug).update(state="off")
    now = timezone.now()

    with use_control():
        worker._hubs(now)
        worker._hubs(now + dt.timedelta(days=2))

    assert ran == []


def test_a_hub_that_fails_is_logged_and_the_others_are_served(hub_a, hub_b, monkeypatch, caplog):
    from base import relay

    real = relay.run

    def broken_in_a(now):
        if current().hub.pk == hub_a.pk:
            raise RuntimeError("the database went away")
        return real(now)

    monkeypatch.setattr(relay, "run", broken_in_a)
    in_b = record(hub_b, hub_b.slug)

    with use_control():
        worker._hubs(timezone.now())

    with use_hub(Hub.objects.get(pk=hub_b.pk)):
        assert OutboxEvent.objects.get(pk=in_b.pk).delivered_at is not None
    assert "worker: the hub tenant-a failed" in caplog.text


def test_the_pass_leaves_no_hubs_connection_open(hub_a, hub_b):
    with use_control():
        worker._hubs(timezone.now())

    open_aliases = {connection.alias for connection in connections.all(initialized_only=True) if connection.connection}
    assert not {f"hub_{hub_a.id.hex}", f"hub_{hub_b.id.hex}"} & open_aliases


def test_the_pass_stops_at_its_budget_and_the_next_tick_goes_on_with_the_next_hub(hub_a, hub_b, monkeypatch):
    served = []
    monkeypatch.setattr(worker, "_serve_hub", lambda hub, now: served.append(hub.slug))
    monkeypatch.setattr(worker, "HUB_PASS_SECONDS", -1.0)  # out of time after the first one

    with use_control():
        worker._hubs(timezone.now())
        worker._hubs(timezone.now())
        worker._hubs(timezone.now())

    # By id, a then b, then a again: every hub gets its turn, however many there are.
    assert served == [hub_a.slug, hub_b.slug, hub_a.slug]


def test_a_hub_that_fails_midway_leaves_no_connection_open_either(hub_a, monkeypatch):
    from base import relay

    def opened_then_broke(now):
        OutboxEvent.objects.exists()  # its connection is open now
        raise RuntimeError("the reaction's server went away")

    monkeypatch.setattr(relay, "run", opened_then_broke)

    with use_control():
        worker._hubs(timezone.now())

    alias = f"hub_{hub_a.id.hex}"
    assert not [connection for connection in connections.all(initialized_only=True) if connection.alias == alias and connection.connection]


@pytest.mark.parametrize("status", [Hub.Status.CANCELLED, Hub.Status.ARCHIVING])
def test_a_business_that_left_still_sends_what_it_owes_the_aeat(hub_a, monkeypatch, status):
    """Re-review of hub#471: a business cancelled (or being archived) with records still to send keeps its outbox
    relayed and its tasks run, VeriFactu's queue first: every ticket with a QR reaches the AEAT (working rules §15). The
    pass over the shared database never looked at a hub's status either."""
    ran = []
    monkeypatch.setattr(scheduler, "_execute", lambda name, scope=None: ran.append((name, scope.key)))
    Hub.objects.filter(pk=hub_a.pk).update(status=status)
    pending = record(hub_a, hub_a.slug)
    now = timezone.now()

    with use_control():
        worker._hubs(now)
        worker._hubs(now + dt.timedelta(minutes=2))

    with use_hub(Hub.objects.get(pk=hub_a.pk)):
        assert OutboxEvent.objects.get(pk=pending.pk).delivered_at is not None
    assert ("verifactu.contingency.process", hub_a.slug) in ran


@pytest.mark.parametrize("status", [Hub.Status.PURGED, Hub.Status.DROPPING, Hub.Status.EXPIRED, Hub.Status.FAILED])
def test_a_hub_whose_database_is_gone_going_or_not_made_is_never_entered(hub_a, monkeypatch, status):
    served = []
    monkeypatch.setattr(worker, "_serve_hub", lambda hub, now: served.append(hub.slug))
    Hub.objects.filter(pk=hub_a.pk).update(status=status)

    with use_control():
        worker._hubs(timezone.now())

    assert served == []


def test_a_demo_whose_time_is_up_is_never_entered(hub_a, monkeypatch):
    served = []
    monkeypatch.setattr(worker, "_serve_hub", lambda hub, now: served.append(hub.slug))
    Hub.objects.filter(pk=hub_a.pk).update(is_demo=True, expires_at=timezone.now() - dt.timedelta(minutes=1))

    with use_control():
        worker._hubs(timezone.now())

    assert served == []


def test_a_hub_moving_to_another_cluster_is_never_entered(hub_a, monkeypatch):
    # Its database is being copied (base.tenancy.move): nothing is relayed nor run in it meanwhile.
    from control.models import Cluster

    served = []
    monkeypatch.setattr(worker, "_serve_hub", lambda hub, now: served.append(hub.slug))
    Hub.objects.filter(pk=hub_a.pk).update(moving_to=Cluster.objects.create(name="next", host="writer-next.example"))

    with use_control():
        worker._hubs(timezone.now())

    assert served == []
