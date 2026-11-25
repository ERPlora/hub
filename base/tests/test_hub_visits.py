"""The worker's visits to the businesses with a database of their own (``base.hub_visits``).

A business's events (``live.OutboxEvent``) and its schedule (``base.TaskSchedule``) live in its own database. The worker
enters it (``use_hub``) only when there is something to do there: when its channel says that one of its operations
committed (the notice ``live.outbox.notify`` sends after the COMMIT, heard on a LISTEN of its own), when the next task
of one of its apps that are on, or the next try of a delivery, comes, or in the look every minute that finds what a
lost notice did not say. In it, the worker relays the outbox, writes its apps' schedule once per process and runs the
tasks due on that business's own scope, as the system, within a time budget per pass and one business's connection at a
time. A business still being prepared is never entered.

Real databases: the session's two hubs (``hub_a``, ``hub_b``; ``base/tenancy/tests/hubs.py``), committed
(``transaction=True``: the relay releases its connections between steps), and a real LISTEN on control's.
"""

import datetime as dt
import threading
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from unittest import mock

import pytest
from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.utils import CursorWrapper
from django.utils import timezone
from live.context import OperationContext, Scope
from live.models import OutboxEvent
from live.operations import get as get_operation

from base import apps_on, catalog, hub_visits, relay, scheduler, worker
from base.catalog.register_apps import RegisterResult
from base.models.activation import AppActivation
from base.models.relay import EventDelivery
from base.models.scheduler import TaskSchedule
from base.services import relay_runs
from base.tenancy.context import current, use_control, use_hub
from base.tenancy.tests import hubs
from control.models import Hub

pytestmark = [
    pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES),
]

EVENT = "demo.item.created"
#: A moment 20 s before a minute: the tasks of every minute are due 20 s after it, long before the look.
BEFORE_A_MINUTE = dt.datetime(2026, 11, 19, 10, 0, 40, tzinfo=dt.UTC)
TICK = dt.timedelta(seconds=5)
LOOK = dt.timedelta(seconds=hub_visits.LOOK_SECONDS)


def fresh(hub: Hub) -> Hub:
    return Hub.objects.select_related("cluster").get(pk=hub.pk)


def record(hub: Hub, slug: str) -> OutboxEvent:
    """An event written without its notice (as one whose notice was lost)."""
    with use_hub(fresh(hub)):
        return OutboxEvent.objects.create(scope_kind="host", scope_key=slug, name=EVENT, payload={"id": "1"})


def create_an_item(hub: Hub) -> None:
    """An operation of the business that records an event: its notice goes on the business's channel after the COMMIT."""
    operation = get_operation("demo.item.create")
    ctx = OperationContext(scope=Scope("host", hub.slug), actor="system", permissions=frozenset({"*"}))
    with use_hub(fresh(hub)):
        operation(ctx, operation.input.model_validate({"name": "Soup"}))


def deliveries(hub: Hub) -> list[tuple[str, str, int]]:
    with use_hub(fresh(hub)):
        return sorted(EventDelivery.objects.values_list("app_label", "status", "attempts"))


def turn_off(hub: Hub, labels) -> None:
    with use_hub(fresh(hub)):
        AppActivation.objects.filter(host=hub.slug, app__in=list(labels)).update(state="off")


def with_tasks() -> set[str]:
    return {task.app_label for task in scheduler.tasks()}


def no_task_due_until_tomorrow(hub: Hub, now: dt.datetime) -> None:
    """Its schedule written, every task of it a day away: nothing but a notice, a delivery's next try or the look
    wakes it (Automations stays on: it hears every event)."""
    with use_hub(fresh(hub)):
        scheduler.sync(now)
        TaskSchedule.objects.update(next_run=now + dt.timedelta(days=1))


@contextmanager
def transactions() -> Iterator[Counter]:
    """How many transactions each alias ran in the block: each one committed or rolled back, and each statement sent
    outside one (autocommit: a transaction of its own); under ``"tasks"``, by alias too, the tasks that ran."""
    counted: Counter = Counter()
    real_commit, real_rollback, real_execute = (
        BaseDatabaseWrapper._commit,
        BaseDatabaseWrapper._rollback,
        CursorWrapper._execute,
    )
    real_claim = relay_runs.run_next_due_task

    def commit(self):
        counted[self.alias] += 1
        return real_commit(self)

    def rollback(self):
        counted[self.alias] += 1
        return real_rollback(self)

    def execute(self, sql, params, *ignored):
        if not self.db.in_atomic_block:
            counted[self.db.alias] += 1
        return real_execute(self, sql, params, *ignored)

    def claim(now, **kwargs):
        outcome = real_claim(now, **kwargs)
        if outcome is not None:
            counted[("tasks", current().alias)] += 1
        return outcome

    with (
        mock.patch.object(BaseDatabaseWrapper, "_commit", commit),
        mock.patch.object(BaseDatabaseWrapper, "_rollback", rollback),
        mock.patch.object(CursorWrapper, "_execute", execute),
        mock.patch.object(relay_runs, "run_next_due_task", claim),
    ):
        yield counted


def serve_until(visits, now: dt.datetime, done, *, seconds: float = 3.0) -> bool:
    """Serve at ``now`` (the clock stands still) until ``done()``, for ``seconds`` of real time at most: a notice
    takes a moment to reach the LISTEN."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        visits.serve(now)
        if done():
            return True
        time.sleep(0.05)
    return False


# ── What a business at rest costs ─────────────────────────────────────────────────────────────────────────────────


def look_every_tick(hub: Hub, now: dt.datetime) -> None:
    """What the worker did in every business on every tick before: its outbox relayed and its due tasks run."""
    scope = Scope("host", hub.slug)
    with use_hub(fresh(hub)):
        relay.run(now)
        scheduler.run_due(now, scope=scope, active=apps_on.active_apps(scope))


def test_a_minute_at_rest_costs_a_business_a_tenth_of_the_transactions_spent_looking_for_work(
    hub_a, hub_b, worker_visits, monkeypatch
):
    """Two businesses at rest with every app on, the same minute: ``hub_b`` looked into on every tick of 5 s as before,
    ``hub_a`` visited by the worker. The same tasks run in both, VeriFactu's queue among them; besides the
    transaction of each task, the worker spends at least ten times fewer looking for work."""
    monkeypatch.setattr(scheduler, "_execute", lambda name, scope=None: None)
    with use_hub(fresh(hub_b)):
        scheduler.sync(BEFORE_A_MINUTE)
    Hub.objects.filter(pk=hub_b.pk).update(status=Hub.Status.REQUESTED)  # the worker leaves it to the old way
    worker_visits.serve(BEFORE_A_MINUTE)
    ticks = [BEFORE_A_MINUTE + TICK * step for step in range(1, 13)]

    with transactions() as counted:
        for now in ticks:
            look_every_tick(hub_b, now)
            worker_visits.serve(now)

    before = counted[hubs.HUB_B_ALIAS] - counted[("tasks", hubs.HUB_B_ALIAS)]
    after = counted[hubs.HUB_A_ALIAS] - counted[("tasks", hubs.HUB_A_ALIAS)]
    assert counted[("tasks", hubs.HUB_A_ALIAS)] == counted[("tasks", hubs.HUB_B_ALIAS)] >= 4
    assert before >= 36 and after * 10 <= before, (before, after)
    with use_hub(fresh(hub_a)):
        queue = TaskSchedule.objects.get(app_label="verifactu", name="process_queue")
    assert queue.last_run is not None and queue.last_run > BEFORE_A_MINUTE


def test_an_event_committed_in_a_business_is_relayed_at_the_next_pass_without_waiting_for_the_look(
    hub_a, hub_b, worker_visits
):
    start = BEFORE_A_MINUTE  # no task of either is due in the next 20 s
    worker_visits.serve(start)

    create_an_item(hub_a)

    with hubs.watched() as sent:
        relayed = serve_until(worker_visits, start + TICK, lambda: any(row[0] == "flow" for row in deliveries(hub_a)))
    assert relayed
    with use_hub(fresh(hub_a)):
        assert not OutboxEvent.objects.filter(delivered_at__isnull=True).exists()
    assert hubs.HUB_B_ALIAS not in sent  # its business committed nothing: it is not entered


def test_an_event_whose_notice_was_lost_is_relayed_by_the_look_and_only_once(hub_a, worker_visits):
    start = BEFORE_A_MINUTE
    no_task_due_until_tomorrow(hub_a, start)
    worker_visits.serve(start)
    lost = record(hub_a, hub_a.slug)

    worker_visits.serve(start + TICK)
    assert deliveries(hub_a) == []  # nothing told the worker yet

    worker_visits.serve(start + LOOK)
    once = deliveries(hub_a)
    another_worker = hub_visits.HubVisits()  # a deploy: the old worker and the new one at once
    try:
        another_worker.serve(start + LOOK)
        worker_visits.serve(start + 2 * LOOK)
    finally:
        another_worker.close()

    assert once and all(status == EventDelivery.Status.DELIVERED and attempts == 1 for _app, status, attempts in once)
    assert deliveries(hub_a) == once
    with use_hub(fresh(hub_a)):
        assert OutboxEvent.objects.get(pk=lost.pk).delivered_at is not None


def test_a_task_due_wakes_its_business_before_the_look(hub_a, worker_visits, monkeypatch):
    ran = []
    monkeypatch.setattr(scheduler, "_execute", lambda name, scope=None: ran.append(name))
    worker_visits.serve(BEFORE_A_MINUTE)

    worker_visits.serve(BEFORE_A_MINUTE + 5 * TICK)  # 25 s: the tasks of every minute came 5 s ago

    assert "verifactu.contingency.process" in ran


def test_a_delivery_tried_again_wakes_its_business_at_its_next_try(hub_a, worker_visits, monkeypatch):
    real = relay.deliver
    failures = []

    def fails_once(app_label, event):
        if app_label == "flow" and not failures:
            failures.append(event.pk)
            raise RuntimeError("the reaction's server went away")
        return real(app_label, event)

    monkeypatch.setattr(relay, "deliver", fails_once)
    start = BEFORE_A_MINUTE
    no_task_due_until_tomorrow(hub_a, start)
    worker_visits.serve(start)
    record(hub_a, hub_a.slug)
    worker_visits.serve(start + LOOK)  # taken; flow's reaction fails and tries again in 2 s
    assert ("flow", EventDelivery.Status.PENDING, 1) in deliveries(hub_a)

    worker_visits.serve(start + LOOK + TICK)

    assert ("flow", EventDelivery.Status.DELIVERED, 2) in deliveries(hub_a)


def test_between_two_looks_of_control_the_visits_read_nothing_there(hub_a, hub_b, worker_visits):
    """The businesses served are read on control at the worker's passes there (``look``), not on every tick."""
    for hub in (hub_a, hub_b):
        no_task_due_until_tomorrow(hub, BEFORE_A_MINUTE)
    worker_visits.serve(BEFORE_A_MINUTE)

    with transactions() as counted:
        for step in range(1, 12):
            worker_visits.serve(BEFORE_A_MINUTE + TICK * step, look=False)

    assert counted["default"] == 0


def test_a_business_no_longer_served_is_left_from_the_next_look(hub_a, hub_b, worker_visits):
    worker_visits.serve(BEFORE_A_MINUTE)
    Hub.objects.filter(pk=hub_b.pk).update(status=Hub.Status.REQUESTED)
    record(hub_b, hub_b.slug)

    with hubs.watched() as sent:
        worker_visits.serve(BEFORE_A_MINUTE + LOOK, look=True)

    assert hubs.HUB_B_ALIAS not in sent


def test_a_task_of_an_app_that_is_off_does_not_wake_its_business(hub_a, worker_visits):
    turn_off(hub_a, with_tasks())
    worker_visits.serve(BEFORE_A_MINUTE)

    with transactions() as counted:
        for step in range(1, 12):  # their time comes 20 s in, before the look
            worker_visits.serve(BEFORE_A_MINUTE + TICK * step)

    assert counted[hubs.HUB_A_ALIAS] == 0


def test_a_task_of_an_app_that_is_off_is_left_as_it_is_while_the_others_run(hub_a, worker_visits, monkeypatch):
    ran = []
    monkeypatch.setattr(scheduler, "_execute", lambda name, scope=None: ran.append(name))
    turn_off(hub_a, with_tasks() - {"verifactu"})
    worker_visits.serve(BEFORE_A_MINUTE)
    with use_hub(fresh(hub_a)):
        waiting = dict(TaskSchedule.objects.filter(app_label="flow").values_list("name", "next_run"))

    worker_visits.serve(BEFORE_A_MINUTE + 5 * TICK)

    with use_hub(fresh(hub_a)):
        untouched = dict(TaskSchedule.objects.filter(app_label="flow").values_list("name", "next_run"))
    assert ran == ["verifactu.contingency.process"]
    assert waiting and untouched == waiting


def test_the_worker_closes_its_listen_on_the_way_out(monkeypatch):
    closed = []
    monkeypatch.setattr(catalog.register_apps, "register_apps", lambda: RegisterResult(written=0, retired=0, docs_changed=0, skipped=True))
    monkeypatch.setattr(hub_visits.HubVisits, "close", lambda self: closed.append(self))
    stop = threading.Event()
    stop.set()

    assert worker.run(stop) == 0
    assert len(closed) == 1


# ── Where and how it serves each business ─────────────────────────────────────────────────────────────────────────


def test_a_hubs_own_outbox_is_relayed_in_its_own_database_and_a_hub_being_prepared_is_not_entered(
    hub_a, hub_b, worker_visits
):
    Hub.objects.filter(pk=hub_b.pk).update(status=Hub.Status.REQUESTED)
    in_a = record(hub_a, hub_a.slug)
    in_b = record(hub_b, hub_b.slug)

    with use_control():
        worker_visits.serve(timezone.now())

    with use_hub(fresh(hub_a)):
        taken = OutboxEvent.objects.get(pk=in_a.pk)
        relayed_to = set(EventDelivery.objects.filter(event=taken).values_list("app_label", flat=True))
    with use_hub(fresh(hub_b)):
        untouched = OutboxEvent.objects.get(pk=in_b.pk)
    assert taken.delivered_at is not None and "flow" in relayed_to
    assert untouched.delivered_at is None


def test_a_hubs_tasks_are_scheduled_in_its_database_and_run_on_its_own_scope(hub_a, worker_visits, monkeypatch):
    ran = []
    monkeypatch.setattr(
        scheduler, "_execute", lambda name, scope=None: ran.append((name, scope.key, current().alias))
    )
    now = timezone.now()

    worker_visits.serve(now)
    with use_hub(fresh(hub_a)):
        scheduled = TaskSchedule.objects.count()
    assert scheduled == len(scheduler.tasks()) and ran == []  # written once, due at their next time

    worker_visits.serve(now + dt.timedelta(days=2))

    assert ran and {(scope, where) for _name, scope, where in ran} == {(hub_a.slug, hubs.HUB_A_ALIAS)}


def test_a_task_of_an_app_the_hub_has_off_is_not_run(hub_a, worker_visits, monkeypatch):
    ran = []
    monkeypatch.setattr(scheduler, "_execute", lambda name, scope=None: ran.append(name))
    turn_off(hub_a, with_tasks())
    now = timezone.now()

    worker_visits.serve(now)
    worker_visits.serve(now + dt.timedelta(days=2))

    assert ran == []


def test_a_hub_that_fails_is_logged_and_the_others_are_served(hub_a, hub_b, worker_visits, monkeypatch, caplog):
    real = relay.take

    def broken_in_a(now):
        if current().hub.pk == hub_a.pk:
            raise RuntimeError("the database went away")
        return real(now)

    monkeypatch.setattr(relay, "take", broken_in_a)
    in_b = record(hub_b, hub_b.slug)

    worker_visits.serve(timezone.now())

    with use_hub(fresh(hub_b)):
        assert OutboxEvent.objects.get(pk=in_b.pk).delivered_at is not None
    assert "worker: the hub tenant-a failed" in caplog.text


def test_a_hub_that_failed_is_tried_again_at_the_next_pass(hub_a, worker_visits, monkeypatch):
    real, failures = relay.take, [RuntimeError("the database went away")]

    def fails_once(now):
        if failures:
            raise failures.pop()
        return real(now)

    monkeypatch.setattr(relay, "take", fails_once)
    start = timezone.now()
    worker_visits.serve(start)
    lost = record(hub_a, hub_a.slug)

    worker_visits.serve(start + TICK)

    with use_hub(fresh(hub_a)):
        assert OutboxEvent.objects.get(pk=lost.pk).delivered_at is not None


def test_a_visit_after_a_notice_that_fails_is_tried_again_at_the_next_pass(hub_a, worker_visits, monkeypatch):
    real, failures = relay.take, [RuntimeError("the database went away")]

    def fails_once(now):
        if failures:
            raise failures.pop()
        return real(now)

    start = BEFORE_A_MINUTE
    no_task_due_until_tomorrow(hub_a, start)
    worker_visits.serve(start)
    monkeypatch.setattr(relay, "take", fails_once)
    create_an_item(hub_a)
    assert serve_until(worker_visits, start + TICK, lambda: not failures)  # its notice heard, the visit failed

    worker_visits.serve(start + 2 * TICK)  # long before the look

    with use_hub(fresh(hub_a)):
        assert not OutboxEvent.objects.filter(delivered_at__isnull=True).exists()


def test_the_events_one_visit_had_no_room_for_are_taken_at_the_next_pass(hub_a, worker_visits, monkeypatch):
    monkeypatch.setattr(relay, "TAKE_PER_TICK", 2)
    start = BEFORE_A_MINUTE
    no_task_due_until_tomorrow(hub_a, start)
    worker_visits.serve(start)
    for _ in range(3):
        record(hub_a, hub_a.slug)

    worker_visits.serve(start + LOOK)
    with use_hub(fresh(hub_a)):
        assert OutboxEvent.objects.filter(delivered_at__isnull=True).count() == 1

    worker_visits.serve(start + LOOK + TICK)  # no notice and long before the next look

    with use_hub(fresh(hub_a)):
        assert not OutboxEvent.objects.filter(delivered_at__isnull=True).exists()


def test_once_its_listen_is_made_again_every_business_is_visited_at_that_pass(hub_a):
    class MadeAgain:
        """An ear with nothing heard at first, then its connection made again: what was notified meanwhile is unknown."""

        answers = [frozenset(), None]

        def heard(self, channels):
            return self.answers.pop(0)

    visits = hub_visits.HubVisits(listener=MadeAgain())
    start = BEFORE_A_MINUTE
    no_task_due_until_tomorrow(hub_a, start)
    visits.serve(start)
    lost = record(hub_a, hub_a.slug)

    visits.serve(start + TICK)  # long before the look

    with use_hub(fresh(hub_a)):
        assert OutboxEvent.objects.get(pk=lost.pk).delivered_at is not None


def test_the_pass_leaves_no_hubs_connection_open(hub_a, hub_b, worker_visits):
    worker_visits.serve(timezone.now())

    open_aliases = {connection.alias for connection in connections.all(initialized_only=True) if connection.connection}
    assert not {hubs.HUB_A_ALIAS, hubs.HUB_B_ALIAS} & open_aliases


def test_the_pass_stops_at_its_budget_and_the_next_one_goes_on_with_the_next_hub(
    hub_a, hub_b, worker_visits, monkeypatch
):
    served = []
    monkeypatch.setattr(worker_visits, "_visit", lambda hub, now, **sweep: served.append(hub.slug))
    monkeypatch.setattr(hub_visits, "HUB_PASS_SECONDS", -1.0)  # out of time after the first one

    worker_visits.serve(timezone.now())
    worker_visits.serve(timezone.now())
    worker_visits.serve(timezone.now())

    # By id, a then b, then a again: every hub gets its turn, however many there are.
    assert served == [hub_a.slug, hub_b.slug, hub_a.slug]


def test_a_hub_that_fails_midway_leaves_no_connection_open_either(hub_a, worker_visits, monkeypatch):
    def opened_then_broke(now):
        OutboxEvent.objects.exists()  # its connection is open now
        raise RuntimeError("the reaction's server went away")

    monkeypatch.setattr(relay, "take", opened_then_broke)

    worker_visits.serve(timezone.now())

    assert not [
        connection
        for connection in connections.all(initialized_only=True)
        if connection.alias == hubs.HUB_A_ALIAS and connection.connection
    ]


@pytest.mark.parametrize("status", [Hub.Status.CANCELLED, Hub.Status.ARCHIVING])
def test_a_business_that_left_still_sends_what_it_owes_the_aeat(hub_a, worker_visits, monkeypatch, status):
    """A business cancelled (or being archived) with records still to send keeps its outbox relayed and its tasks
    run, VeriFactu's queue first: every ticket with a QR reaches the AEAT."""
    ran = []
    monkeypatch.setattr(scheduler, "_execute", lambda name, scope=None: ran.append((name, scope.key)))
    Hub.objects.filter(pk=hub_a.pk).update(status=status)
    pending = record(hub_a, hub_a.slug)
    now = timezone.now()

    worker_visits.serve(now)
    worker_visits.serve(now + dt.timedelta(minutes=2))

    with use_hub(fresh(hub_a)):
        assert OutboxEvent.objects.get(pk=pending.pk).delivered_at is not None
    assert ("verifactu.contingency.process", hub_a.slug) in ran


def served_by(visits, monkeypatch) -> list[str]:
    served: list[str] = []
    monkeypatch.setattr(visits, "_visit", lambda hub, now, **sweep: served.append(hub.slug))
    visits.serve(timezone.now())
    return served


@pytest.mark.parametrize("status", [Hub.Status.PURGED, Hub.Status.DROPPING, Hub.Status.EXPIRED, Hub.Status.FAILED])
def test_a_hub_whose_database_is_gone_going_or_not_made_is_never_entered(hub_a, worker_visits, monkeypatch, status):
    Hub.objects.filter(pk=hub_a.pk).update(status=status)

    assert served_by(worker_visits, monkeypatch) == []


def test_a_demo_whose_time_is_up_is_never_entered(hub_a, worker_visits, monkeypatch):
    Hub.objects.filter(pk=hub_a.pk).update(is_demo=True, expires_at=timezone.now() - dt.timedelta(minutes=1))

    assert served_by(worker_visits, monkeypatch) == []


def test_a_hub_being_restored_or_moving_to_another_cluster_is_never_entered(hub_a, worker_visits, monkeypatch):
    # Its database is being put back as it was at a moment (base.tenancy.restore) or copied to another cluster
    # (base.tenancy.move): nothing is relayed nor run in it meanwhile.
    from control.models import Cluster

    Hub.objects.filter(pk=hub_a.pk).update(
        restoring_from=Cluster.objects.create(name="restore", host="writer-restore.example", is_open=False)
    )
    assert served_by(worker_visits, monkeypatch) == []

    Hub.objects.filter(pk=hub_a.pk).update(
        restoring_from=None, moving_to=Cluster.objects.create(name="next", host="writer-next.example")
    )
    assert served_by(worker_visits, monkeypatch) == []
