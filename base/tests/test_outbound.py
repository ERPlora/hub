"""Slow I/O after the COMMIT, off the loop that committed (``base.outbound``).

The worker relays the outbox of every hub in one loop, and Django runs what a transaction leaves for after its COMMIT
right there: a reaction that calls another system would hold every other delivery until it answered. ``after_commit``
hands that I/O to a few threads of the worker's own, after the COMMIT and never after a rollback, in the database of
the hub that asked; the loop goes on at once. These tests drive real threads on the real database: a job waits until
the test lets it (``WAIT`` at most, so a broken pool fails instead of hanging), and the order says who waited for whom.
"""

import logging
import threading
import time
from dataclasses import FrozenInstanceError

import pytest
from django.db import connection, connections
from live.context import OperationContext, Scope
from live.models import OutboxEvent
from live.operations import Operation
from ninja import Schema

from base import outbound
from base.models import Hub
from base.models.identity import HubIdentity
from base.tenancy import context
from base.tenancy.tests import hubs
from base.tenancy.tests.business import A, HUB_DB, HUB_DB_COMMITTED

#: The platform's (``base.registry.REGISTRY_SCOPE``): its operations run on control from anywhere.
PLATFORM = Scope("platform", "registry")
#: The most a test waits for a thread.
WAIT = 5
#: Where the pool's own tests run their jobs: control's, the platform's, whose tables are in ``default``.
CONTROL = context.CONTROL_DATABASE


class Done(Schema):
    count: int = 0


def command(fn) -> Operation:
    """A command as a ``services.py`` declares it, not registered: ``fn(ctx, data)`` runs in its transaction."""
    return Operation(
        name="base.probe.run", kind="command", permission=None, input=Schema, output=Done, expose_api=False, ai=None, fn=fn
    )


def as_system(scope: Scope = A) -> OperationContext:
    return OperationContext(scope=scope, actor="system", permissions=frozenset())


def eventually(condition, *, seconds: float = WAIT) -> bool:
    """Whether ``condition()`` holds within ``seconds`` (a thread's work, seen from the test)."""
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.01)
    return True


@pytest.fixture
def pool():
    """A pool of the test's own, stopped after it: ``pool(threads=…, queued=…)``."""
    made: list[outbound.Pool] = []

    def make(**sizes) -> outbound.Pool:
        made.append(outbound.Pool(**sizes))
        return made[-1]

    yield make
    for each in made:
        assert each.stop(grace=WAIT), "a job of the test was still running"


def job_here(fn, *args) -> outbound.Job:
    """A job of ``fn(*args)`` in the database context that runs now, as ``after_commit`` builds it."""
    return outbound.Job(fn, args, context.current())


# ── After the COMMIT, in a thread of its own: the operation never waits for it ────────────────────────────────────


@pytest.mark.outbound_threads
@HUB_DB_COMMITTED
def test_a_job_runs_after_the_commit_in_a_thread_of_its_own_and_the_operation_never_waits(hub_a):
    test_thread, seen, let_go, finished = threading.current_thread(), [], threading.Event(), threading.Event()

    def job(scope, event_id):
        let_go.wait(WAIT)  # the operation, and the test, go on meanwhile
        seen.append(
            (threading.current_thread() is not test_thread, OutboxEvent.objects.filter(pk=event_id).exists(), let_go.is_set())
        )
        finished.set()

    def fn(ctx, data):
        event = OutboxEvent.objects.create(scope_kind=ctx.scope.kind, scope_key=ctx.scope.key, name="base.probe.ran", payload={})
        outbound.after_commit(job, ctx.scope, event.pk)
        return {"count": 1}

    with context.use_hub(hub_a):
        command(fn)(as_system(), Schema())
    let_go.set()

    assert finished.wait(WAIT)
    # Another thread, what the operation wrote is committed, and the operation had returned before it went on.
    assert seen == [(True, True, True)]


@pytest.mark.outbound_threads
@HUB_DB_COMMITTED
def test_an_operation_that_is_undone_sends_nothing(pool, monkeypatch, hub_a):
    monkeypatch.setattr(outbound, "_pool", pool(threads=1))
    ran: list[str] = []

    def job(scope, name):
        ran.append(name)

    def undone(ctx, data):
        outbound.after_commit(job, ctx.scope, "undone")
        raise RuntimeError("the business said no")

    def kept(ctx, data):
        outbound.after_commit(job, ctx.scope, "kept")
        return {"count": 1}

    with context.use_hub(hub_a):
        with pytest.raises(RuntimeError):
            command(undone)(as_system(), Schema())
        command(kept)(as_system(), Schema())

    # One thread, in order: had the undone one been sent, it would have run first.
    assert eventually(lambda: ran == ["kept"])


@HUB_DB
def test_after_commit_outside_an_operation_is_a_misuse(hub_a):
    from live.errors import LiveMisuse

    with context.use_hub(hub_a), pytest.raises(LiveMisuse):
        outbound.after_commit(print, "nothing")


# ── In the database of the hub that asked, and nothing of it left in the thread ──────────────────────────────────


@pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)
def test_each_job_runs_in_the_database_of_the_hub_that_asked_and_leaves_nothing_behind(hub_a, hub_b, pool):
    # As in production: a thread of its own has no context.
    one_thread, seen = pool(threads=1), []

    def where(name):
        hub = context.current_hub()
        identities = [str(found) for found in HubIdentity.objects.values_list("hub_id", flat=True)] if hub else None
        seen.append((name, hub.slug if hub else None, identities))

    with context.use_hub(hub_a):
        one_thread.submit(job_here(where, "a"))
    with context.use_hub(hub_b):
        one_thread.submit(job_here(where, "b"))
    with context.use_control():
        one_thread.submit(job_here(where, "control"))

    assert eventually(lambda: len(seen) == 3)
    assert seen == [
        ("a", "tenant-a", [str(hubs.HUB_A_ID)]),
        ("b", "tenant-b", [str(hubs.HUB_B_ID)]),
        ("control", None, None),  # control has no hub's identity: the job of the platform reads none
    ]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)
def test_a_job_of_a_hub_with_its_own_database_reaches_it_from_a_fresh_thread(hub_a, pool):
    seen = []
    with context.use_hub(hub_a):
        job = job_here(lambda: seen.append(context.current_alias()))
    pool(threads=1).submit(job)

    assert eventually(lambda: seen != [])
    assert seen == [job.database.alias] and seen != ["default"]


# ── For the business of its row: never another hub's database ─────────────────────────────────────────────────────────


def for_its_business(seen: list):
    """A job that runs an operation of the business it is for, as the inbox's delivery does: where its thread works
    (the context's kind, its alias, the identities of the hubs it sees) and whether that operation ran."""

    def job(scope):
        active = context.current()
        identities = sorted(str(found) for found in HubIdentity.objects.values_list("hub_id", flat=True))
        try:
            command(lambda ctx, data: {"count": 1})(as_system(scope), Schema())
            outcome = "ran"
        except context.HubContextMismatch:
            outcome = "HubContextMismatch"
        seen.append((scope.key, active.kind, active.alias, identities, outcome))

    return job


@pytest.mark.outbound_threads
@pytest.mark.django_db(databases=hubs.HUB_DATABASES, transaction=True)
def test_a_job_for_another_hub_never_reaches_its_database(hub_a, hub_b, pool, monkeypatch):
    """A hub's database holds only its own rows. A job it says is for another hub stays in its database, sees only its
    rows and the other's operation is refused; one for the platform runs on control. No job ever reaches another hub's
    database (there is no shared database to hand it to)."""
    monkeypatch.setattr(outbound, "_pool", pool(threads=1))
    seen: list = []
    job = for_its_business(seen)
    tenant_a, tenant_b = Scope("host", hub_a.slug), Scope("host", hub_b.slug)

    def ask(ctx, data):
        outbound.after_commit(job, tenant_b)
        return {"count": 1}

    def ask_the_platform(ctx, data):
        outbound.after_commit(job, PLATFORM)
        return {"count": 1}

    with context.use_hub(hub_a):
        command(ask)(as_system(tenant_a), Schema())
        command(ask_the_platform)(as_system(tenant_a), Schema())

    assert eventually(lambda: len(seen) == 2)
    assert seen == [
        ("tenant-b", context.HUB, hubs.HUB_A_ALIAS, [str(hubs.HUB_A_ID)], "HubContextMismatch"),
        ("registry", context.HUB, hubs.HUB_A_ALIAS, [str(hubs.HUB_A_ID)], "ran"),
    ]


@HUB_DB
def test_whom_a_job_is_for_is_kept_from_when_it_is_asked(hub_a):
    """The context a job runs in is chosen when it is asked and never changes after: nobody hands it another hub's."""
    with context.use_hub(hub_a):
        job = outbound.Job(print, (), context.current())
    with pytest.raises(FrozenInstanceError):
        job.database = context.CONTROL_DATABASE  # type: ignore[misc]
    assert job.database.hub is hub_a


# ── Bounded: a few at once, a queue with a limit, the same job never twice ───────────────────────────────────────


def test_at_most_its_threads_run_at_once(pool):
    two, let_go, running, most = pool(threads=2), threading.Event(), [], []
    lock = threading.Lock()

    def job(n):
        with lock:
            running.append(n)
            most.append(len(running))
        let_go.wait(WAIT)
        with lock:
            running.remove(n)

    for n in range(5):
        assert two.submit(outbound.Job(job, (n,), CONTROL))
    assert eventually(lambda: len(running) == 2)
    time.sleep(0.1)  # a third thread, had there been one, would have started by now
    assert len(running) == 2
    let_go.set()
    assert eventually(lambda: len(most) == 5 and not running)
    assert max(most) == 2


def test_the_same_job_already_waiting_is_not_queued_twice(pool):
    one, let_go, ran = pool(threads=1), threading.Event(), []

    def job(run_id):
        ran.append(run_id)
        let_go.wait(WAIT)

    assert one.submit(outbound.Job(job, ("r1",), CONTROL))
    assert eventually(lambda: ran == ["r1"])  # running
    assert one.submit(outbound.Job(job, ("r2",), CONTROL))  # waits
    assert not one.submit(outbound.Job(job, ("r2",), CONTROL))  # a sweep sends it again: not twice
    # r1 runs, it no longer waits: the next step of its run may need it again (its claim says whether it goes).
    assert one.submit(outbound.Job(job, ("r1",), CONTROL))
    let_go.set()
    assert eventually(lambda: ran == ["r1", "r2", "r1"])


def test_past_its_queue_a_job_is_dropped_with_a_warning_and_its_app_sends_it_again(pool, caplog):
    one, let_go, ran = pool(threads=1, queued=1), threading.Event(), []

    def job(n):
        ran.append(n)
        let_go.wait(WAIT)

    assert one.submit(outbound.Job(job, (1,), CONTROL))
    assert eventually(lambda: ran == [1])
    assert one.submit(outbound.Job(job, (2,), CONTROL))  # waits: the queue holds one
    with caplog.at_level(logging.WARNING, logger="base.outbound"):
        assert not one.submit(outbound.Job(job, (3,), CONTROL))
    let_go.set()
    assert eventually(lambda: ran == [1, 2])
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert "job" in caplog.records[0].getMessage() and "dropped" in caplog.records[0].getMessage()


# ── Failures, connections and the stop ──────────────────────────────────────────────────────────────────────────


def test_a_job_that_fails_is_logged_with_its_traceback_and_the_others_go_on(pool, caplog):
    one, ran = pool(threads=1), []

    def broken(run_id):
        raise ConnectionError("the other system hung up")

    def fine(run_id):
        ran.append(run_id)

    with caplog.at_level(logging.ERROR, logger="base.outbound"):
        one.submit(outbound.Job(broken, ("r1",), CONTROL))
        one.submit(outbound.Job(fine, ("r2",), CONTROL))
        assert eventually(lambda: ran == ["r2"])
    failed = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(failed) == 1 and failed[0].exc_info is not None
    assert "broken" in failed[0].getMessage() and "r1" in failed[0].getMessage()


@pytest.mark.django_db(transaction=True)
def test_a_job_gives_its_connection_back_before_it_waits_and_when_it_ends(pool):
    one, seen, finished = pool(threads=1), {}, threading.Event()

    def job():
        Hub.objects.exists()  # its claim, in a transaction of its own
        seen["claimed"] = connection.connection is not None
        outbound.release()  # …then it waits on the network with no connection held
        seen["waiting"] = connection.connection is not None
        Hub.objects.exists()  # its record, on a connection taken again
        seen["wrapper"] = connections["default"]  # this thread's own, not the proxy the test would read as its own
        finished.set()

    one.submit(outbound.Job(job, (), CONTROL))

    assert finished.wait(WAIT)
    assert eventually(lambda: seen["wrapper"].connection is None)  # given back when the job ended
    assert (seen["claimed"], seen["waiting"]) == (True, False)


@HUB_DB_COMMITTED
def test_release_inside_an_operation_is_refused_and_its_transaction_kept(hub_a, pool):
    one, seen, finished = pool(threads=1), [], threading.Event()

    def fn(ctx, data):
        try:
            outbound.release()  # its transaction is open: closing the connection would lose it
        except RuntimeError:
            seen.append("refused")
        seen.append(HubIdentity.objects.exists())  # …and it still reads on it
        return {"count": 1}

    def job():
        command(fn)(as_system(), Schema())
        finished.set()

    with context.use_hub(hub_a):
        one.submit(job_here(job))

    assert finished.wait(WAIT)
    assert seen == ["refused", True]


@HUB_DB
def test_release_outside_a_job_of_the_pool_changes_nothing(hub_a):
    with context.use_hub(hub_a):
        HubIdentity.objects.exists()
        outbound.release()  # the test's own transaction, or a request's: never closed under them
        business = connections[context.current_alias()]
    assert business.connection is not None and business.in_atomic_block


def test_stop_drops_what_waits_and_gives_what_runs_its_grace(pool, caplog):
    one, let_go, ran = pool(threads=1), threading.Event(), []

    def job(n):
        ran.append(n)
        let_go.wait(WAIT)

    one.submit(outbound.Job(job, (1,), CONTROL))
    assert eventually(lambda: ran == [1])
    one.submit(outbound.Job(job, (2,), CONTROL))

    with caplog.at_level(logging.WARNING, logger="base.outbound"):
        started = time.monotonic()
        assert one.stop(grace=0.2) is False  # 1 still runs: left to its lease
        assert time.monotonic() - started < 2
        assert not one.submit(outbound.Job(job, (3,), CONTROL))  # a stopped pool takes nothing
    messages = [record.getMessage() for record in caplog.records]
    assert any("waited" in message and "dropped" in message for message in messages)
    assert any("still running" in message for message in messages)
    let_go.set()
    assert one.stop(grace=WAIT) is True  # stopping again waits for what still ran
    assert ran == [1]  # 2 waited, and was dropped


def test_stop_returns_once_what_runs_ends_within_its_grace(pool):
    one, let_go, ran = pool(threads=2), threading.Event(), []

    def job(n):
        let_go.wait(WAIT)
        ran.append(n)

    one.submit(outbound.Job(job, (1,), CONTROL))
    threading.Timer(0.1, let_go.set).start()

    assert one.stop(grace=WAIT) is True
    assert ran == [1]


def test_a_pool_that_never_ran_a_job_stops_at_once():
    assert outbound.Pool().stop(grace=WAIT) is True
