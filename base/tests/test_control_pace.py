"""When the worker's steps on control run (``base.control_pace``).

Control's steps (the platform's outbox, the list of businesses the visits serve, the apps to set up, the hubs due in
``hub_due``, the data work, the moves and the reaper) no longer look for work on every tick of 5 s: they run in a pass
of their own when the platform's channel is notified after a COMMIT, when a time control keeps comes, after a pass that
worked, or in the look every minute that finds what a lost notice did not say.

Real databases: control and the session's two hubs (``hub_a``, ``hub_b``; ``base/tenancy/tests/hubs.py``), committed
(``transaction=True``), and the worker's real LISTEN on control's.
"""

import datetime as dt
import logging
import threading
import time
from collections import Counter
from contextlib import contextmanager
from unittest import mock

import pytest
from django.db import connection, transaction
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.utils import CursorWrapper
from live.context import Scope, system_context
from live.operations import get as get_operation

from base import catalog, control_pace, events, hub_listener, queries, registry, scheduler, services, worker
from base import worker_activations, worker_data
from base.catalog import RegisterResult
from base.hub_listener import Listener
from base.models.activation import AppActivation
from base.models.scheduler import TaskSchedule
from base.schemas.hub_registry import HubRegistryIn
from base.tenancy import provision
from base.tenancy.context import use_control, use_hub
from base.tenancy.tests import hubs
from base.tests.test_worker import Inline
from control.models import Hub, HubDue

pytestmark = [pytest.mark.django_db(transaction=True, databases=hubs.HUB_DATABASES)]

SKIPPED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)
START = dt.datetime(2026, 11, 19, 10, 0, 40, tzinfo=dt.UTC)
TICK = dt.timedelta(seconds=5)
A_MINUTE = [START + TICK * step for step in range(1, 13)]


@pytest.fixture
def at_rest(hub_a, hub_b, monkeypatch):
    """Two businesses served with no task due for a day, the slow passes inline (the data and moves passes count),
    the night already measured."""
    for hub in (hub_a, hub_b):
        with use_hub(Hub.objects.select_related("cluster").get(pk=hub.pk)):
            scheduler.sync(START)
            TaskSchedule.objects.update(next_run=START + dt.timedelta(days=1))
    monkeypatch.setattr(catalog, "register_apps", lambda: SKIPPED)
    monkeypatch.setattr(worker, "Background", Inline)
    monkeypatch.setattr(worker_data, "_measured", dt.date.max)


@contextmanager
def on_control() -> Counter:
    """The transactions control's alias ran while ``counting["on"]``: each committed or rolled back, and each statement
    sent outside one."""
    counted: Counter = Counter()
    real_commit, real_rollback, real_execute = (
        BaseDatabaseWrapper._commit,
        BaseDatabaseWrapper._rollback,
        CursorWrapper._execute,
    )

    def commit(self):
        if counted["on"] and self.alias == "default":
            counted["transactions"] += 1
        return real_commit(self)

    def rollback(self):
        if counted["on"] and self.alias == "default":
            counted["transactions"] += 1
        return real_rollback(self)

    def execute(self, sql, params, *ignored):
        if counted["on"] and self.db.alias == "default" and not self.db.in_atomic_block:
            counted["transactions"] += 1
        return real_execute(self, sql, params, *ignored)

    with (
        mock.patch.object(BaseDatabaseWrapper, "_commit", commit),
        mock.patch.object(BaseDatabaseWrapper, "_rollback", rollback),
        mock.patch.object(CursorWrapper, "_execute", execute),
    ):
        yield counted


def every_tick_before(now: dt.datetime) -> None:
    """What the worker did on control on every tick of 5 s before: the freeze switch, the platform's outbox, the list
    of businesses served, the apps to set up, the data work, the moves and the hubs due."""
    worker._frozen()
    worker._relay(now)
    with use_control():
        services.provisioning.hubs_to_serve(now)
        services.activation.hubs_visited_since(now.date())
    worker_activations._activations(now)
    worker_data._data(now)
    worker_data._moves(now)
    worker._due(now)


def run_the_worker(ticks: list[dt.datetime], counted: Counter, *, databases_only: bool = False, between=None) -> None:
    """The worker's loop: its first tick at ``START``, then one at each of ``ticks``, counted; ``between(tick)`` runs
    after the tick of that number, and a notice it sends gets a moment to reach the LISTEN."""
    stop = threading.Event()
    times = [START, *ticks]

    def wait(seconds: float) -> bool:
        counted["on"] = 1
        if between is not None and between(len(ticks) - len(times)):
            time.sleep(0.3)
        if len(times) == 0:
            stop.set()
        return stop.is_set()

    assert worker.run(stop, wait=wait, clock=lambda: times.pop(0), databases_only=databases_only) == 0


def test_a_minute_at_rest_costs_control_a_tenth_of_the_transactions_spent_looking_for_work(at_rest):
    """The same minute, two businesses at rest: control's steps on every tick of 5 s as before, then the worker's
    loop; the loop spends at least ten times fewer transactions on control."""
    every_tick_before(START)
    with on_control() as before:
        before["on"] = 1
        for now in A_MINUTE:
            every_tick_before(now)
        worker._reap(A_MINUTE[-1])

    with on_control() as after:
        run_the_worker(A_MINUTE, after)

    assert before["transactions"] >= 150 and after["transactions"] * 10 <= before["transactions"], (
        before["transactions"],
        after["transactions"],
    )


# ── What wakes control's steps ────────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def due_passes(at_rest, monkeypatch) -> list[dt.datetime]:
    """The clock of each pass over ``hub_due`` the worker's loop makes (``provision.run_due``, which works on nothing)."""
    passes: list[dt.datetime] = []
    monkeypatch.setattr(provision, "run_due", lambda now: passes.append(now) or 0)
    return passes


def sign_up(tick: int) -> bool:
    """After the second tick, the SaaS registers a business: an operation of the platform, committed."""
    if tick != 2:
        return False
    get_operation("base.hub.register")(
        system_context(registry.REGISTRY_SCOPE),
        HubRegistryIn(id="0199c4b0-0000-7000-8000-0000000018a4", slug="nuevo", name="Nuevo", country="ES",
                      timezone="Europe/Madrid", language="es", vertical="restaurant"),
    )
    return True


def test_a_sign_up_is_worked_on_at_the_next_tick_without_waiting_for_the_look(due_passes):
    run_the_worker(A_MINUTE[:5], Counter(), between=sign_up)

    # Its pass relayed the registration's event in control's outbox, so the next tick looks again; then it rests.
    assert due_passes == [START, A_MINUTE[2], A_MINUTE[3]]


def ring_lost(tick: int) -> bool:
    """After the second tick, a hub is rung in ``hub_due`` whose notice never came."""
    if tick == 2:
        HubDue.mark_due(Hub.objects.get(pk=hubs.HUB_A_ID), A_MINUTE[1])
    return False


@pytest.mark.parametrize("databases_only", [False, True], ids=["worker", "databases-only"])
def test_a_ring_whose_notice_was_lost_waits_for_the_look(due_passes, databases_only):
    after_the_look = [A_MINUTE[-1] + TICK, A_MINUTE[-1] + 2 * TICK]

    run_the_worker(A_MINUTE + after_the_look, Counter(), databases_only=databases_only, between=ring_lost)

    # The look served the ring's hub (its apps to set up), so the next tick looks again; then it rests.
    assert due_passes == [START, A_MINUTE[-1], after_the_look[0]]


@pytest.mark.parametrize("outcome", [1, RuntimeError("the database went away")], ids=["made-one", "failed"])
def test_a_pass_over_hub_due_that_made_a_hub_or_failed_looks_again_at_the_next_tick(at_rest, monkeypatch, outcome):
    passes, outcomes = [], [outcome]

    def run_due(now):
        passes.append(now)
        answer = outcomes.pop() if outcomes else 0
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(provision, "run_due", run_due)

    run_the_worker(A_MINUTE, Counter())

    # Then it rests: its look comes a minute after that second pass.
    assert passes == [START, A_MINUTE[0]]


def test_the_worker_with_databases_only_hears_a_sign_up_too(due_passes):
    run_the_worker(A_MINUTE[:4], Counter(), databases_only=True, between=sign_up)

    assert due_passes == [START, A_MINUTE[2]]


class Deaf:
    """An ear that hears nothing, unless ``ring`` says it heard the platform's channel."""

    def __init__(self) -> None:
        self.ring = False

    def rung(self) -> bool:
        rung, self.ring = self.ring, False
        return rung


def test_a_time_kept_in_hub_due_wakes_the_pass_then(hub_a):
    pace = control_pace.ControlPace(Deaf())
    assert pace.due(START)
    HubDue.mark_due(hub_a, START + dt.timedelta(seconds=20))  # a retry's time
    pace.ran(START, worked=False)

    assert [pace.due(START + TICK * step) for step in range(1, 5)] == [False, False, False, True]


def test_a_pass_that_worked_looks_again_at_the_next_tick(db):
    pace = control_pace.ControlPace(Deaf())
    pace.ran(START, worked=True)
    assert pace.due(START + TICK)

    pace.ran(START + TICK, worked=False)

    assert not pace.due(START + 2 * TICK)
    assert pace.due(START + TICK + dt.timedelta(seconds=control_pace.LOOK_SECONDS))
    assert not pace.due(START + TICK + dt.timedelta(seconds=control_pace.LOOK_SECONDS - 1))


def test_the_moves_pass_starts_on_the_first_pass_then_on_a_notice_or_every_ten_minutes(db):
    ear = Deaf()
    pace = control_pace.ControlPace(ear)
    moves_look = dt.timedelta(seconds=control_pace.MOVES_LOOK_SECONDS)
    assert pace.due(START) and pace.moves_due(START)
    pace.moved(START, started=True)
    pace.ran(START, worked=False)

    look = START + dt.timedelta(seconds=control_pace.LOOK_SECONDS)
    assert pace.due(look) and not pace.moves_due(look)  # the look alone does not start it
    pace.ran(look, worked=False)
    ear.ring = True  # the staff asked for a move, a restore or a copy
    assert pace.due(look + TICK) and pace.moves_due(look + TICK)
    pace.moved(look + TICK, started=True)
    pace.ran(look + TICK, worked=False)

    later = look + TICK + moves_look
    assert pace.due(later) and pace.moves_due(later)
    assert not pace.moves_due(later - dt.timedelta(seconds=1))


def test_a_moves_pass_that_could_not_start_starts_at_the_next_pass(db):
    ear = Deaf()
    pace = control_pace.ControlPace(ear)
    pace.due(START)
    pace.moved(START, started=True)
    pace.ran(START, worked=False)
    ear.ring = True  # a second move asked while the first is copying
    assert pace.due(START + TICK) and pace.moves_due(START + TICK)
    pace.moved(START + TICK, started=False)  # the first one still runs: one at a time
    pace.ran(START + TICK, worked=False)

    look = START + TICK + dt.timedelta(seconds=control_pace.LOOK_SECONDS)
    assert pace.due(look) and pace.moves_due(look)
    pace.moved(look, started=True)
    pace.ran(look, worked=False)
    second_look = look + dt.timedelta(seconds=control_pace.LOOK_SECONDS)
    assert pace.due(second_look) and not pace.moves_due(second_look)


def test_a_move_asked_for_its_night_starts_the_moves_pass_then(hub_a):
    from control.models import Cluster

    pace = control_pace.ControlPace(Deaf())
    pace.due(START)
    pace.moved(START, started=True)
    elsewhere = Cluster.objects.create(name="tonight", host="writer-tonight.example")
    night = START + dt.timedelta(seconds=20)
    Hub.objects.filter(pk=hub_a.pk).update(move_scheduled_to=elsewhere, move_scheduled_for=night)
    pace.ran(START, worked=False)

    assert not pace.due(night - TICK)
    assert pace.due(night) and pace.moves_due(night)


def test_a_time_kept_that_cannot_be_read_is_logged_and_left_to_the_look(db, monkeypatch, caplog):
    monkeypatch.setattr(queries.due_work, "next_on_control", lambda now: 1 / 0)
    pace = control_pace.ControlPace(Deaf())

    with caplog.at_level(logging.ERROR, logger="base.control_pace"):
        pace.ran(START, worked=False)

    assert not pace.due(START + TICK)
    assert pace.due(START + dt.timedelta(seconds=control_pace.LOOK_SECONDS))
    assert "the next time control keeps could not be read" in caplog.text


# ── One LISTEN for the visits and for control ─────────────────────────────────────────────────────────────────────

A, B = "live_host_pace_a", "live_host_pace_b"


def notify(channel: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_notify(%s, %s)", [channel, '{"events":["demo.item.created"]}'])


def soon(check, *, seconds: float = 3.0):
    """``check()`` again until it gives something, for ``seconds`` of real time at most."""
    deadline = time.monotonic() + seconds
    while not (found := check()) and time.monotonic() < deadline:
        time.sleep(0.05)
    return found


@pytest.fixture
def ear():
    listening = control_pace.Ear()
    yield listening
    listening.close()


def test_a_new_connection_counts_as_every_channel_heard_by_both(ear):
    assert ear.rung()
    assert ear.heard({A, B}) is None
    assert not ear.rung()
    assert ear.heard({A, B}) == frozenset()


def test_what_the_platforms_channel_says_is_controls_and_what_a_business_says_waits_for_the_visits(ear):
    ear.rung(), ear.heard({A, B})

    notify(A)
    notify(control_pace.CHANNEL)

    assert soon(ear.rung)
    assert ear.heard({A, B}) == {A}
    assert not ear.rung()

    notify(control_pace.CHANNEL)
    time.sleep(0.3)
    assert ear.heard({A, B}) == frozenset()  # the visits' call takes it off the connection: it is kept for control
    assert ear.rung()


def test_the_visits_and_control_share_one_connection(db):
    made = []
    shared = control_pace.Ear(Listener(connect=lambda: made.append(1) or hub_listener.connect()))
    try:
        shared.rung(), shared.heard({A}), shared.rung(), shared.heard({A, B})
    finally:
        shared.close()

    assert made == [1]


# ── What tells control's steps ────────────────────────────────────────────────────────────────────────────────────


def test_a_ring_from_a_business_tells_the_worker_after_controls_commit(ear, hub_a):
    ear.rung()
    with transaction.atomic():
        services.provisioning.ring(hub_a, told=events.APP_ACTIVATION_REQUESTED)
        time.sleep(0.2)
        assert not ear.rung()  # not before the COMMIT

    assert soon(ear.rung)
    assert HubDue.objects.get(pk=hub_a.pk).due_at <= dt.datetime.now(dt.UTC)


def test_a_business_turning_on_an_app_its_database_lacks_tells_the_worker(ear, hub_a):
    ear.rung()
    Hub.objects.filter(pk=hub_a.pk).update(schema_apps={})  # its database lacks every app's tables
    operation = get_operation("base.app.enable")
    ctx = system_context(Scope("host", hub_a.slug))

    with use_hub(Hub.objects.select_related("cluster").get(pk=hub_a.pk)):
        AppActivation.objects.filter(host=hub_a.slug, app="printing").update(state="off", chosen=False)
        answer = operation(ctx, operation.input.model_validate({"app": "printing"}))

    assert answer.state == "creating"
    assert soon(ear.rung)


# ── A slow pass takes one hub at a time: the next one does not wait for the look ──────────────────────────────────


def asked_after_the_second_tick(queue: list[str], *asked: str):
    """After the second tick the staff asks for ``asked``, each an operation of the platform: its notice."""

    def between(tick: int) -> bool:
        if tick != 2:
            return False
        queue.extend(asked)
        notify(control_pace.CHANNEL)
        return True

    return between


def test_the_second_of_two_moves_asked_is_taken_at_the_tick_after_the_first_ended(at_rest, monkeypatch):
    """``move.run_due`` moves one hub a pass (a copy takes a while): the one asked after it starts at the next tick,
    as it did when the moves' pass started on every tick, not at the moves' look ten minutes later."""
    queue, moved = [], []
    monkeypatch.setattr(worker_data.move, "run_due", lambda now, cancelled=None: 1 if queue and not moved.append((queue.pop(0), now)) else 0)

    run_the_worker(A_MINUTE, Counter(), between=asked_after_the_second_tick(queue, "first", "second"))

    assert moved == [("first", A_MINUTE[2]), ("second", A_MINUTE[3])]


def test_the_second_of_two_resets_asked_is_taken_at_the_tick_after_the_first_ended(at_rest, monkeypatch):
    """The data pass takes one hub at a time (its copy takes a while): the next one due starts at the next tick, not
    at the look a minute later."""
    queue, taken = [], []

    def claim(now, lease):
        if queue:
            taken.append((queue.pop(0), now))
        return taken[-1][0] if taken and taken[-1][1] == now else None

    monkeypatch.setattr(services.offboarding, "claim_next_data_hub", claim)
    monkeypatch.setattr(services.provisioning, "registry_row", lambda hub_id: None)
    monkeypatch.setattr(services.provisioning, "release_hub", lambda hub_id, now: None)

    run_the_worker(A_MINUTE[:6], Counter(), between=asked_after_the_second_tick(queue, "first", "second"))

    assert taken == [("first", A_MINUTE[2]), ("second", A_MINUTE[3])]


def test_a_moves_pass_that_failed_starts_again_at_the_next_tick(at_rest, monkeypatch):
    queue, passes = [], []

    def run_due(now, cancelled=None):
        passes.append(now)
        if queue:
            raise RuntimeError(f"the database went away during the {queue.pop()} move")
        return 0

    monkeypatch.setattr(worker_data.move, "run_due", run_due)

    run_the_worker(A_MINUTE, Counter(), between=asked_after_the_second_tick(queue, "first"))

    # Then it rests: nothing was left to move.
    assert passes == [START, A_MINUTE[2], A_MINUTE[3]]


def test_a_slow_pass_that_raises_tells_the_pace_too(db):
    pace = control_pace.ControlPace(Deaf())
    pace.ran(START, worked=False)

    with pytest.raises(ZeroDivisionError):
        pace.telling(lambda: 1 / 0)()

    assert pace.due(START + TICK) and pace.moves_due(START + TICK)
    pace.ran(START + TICK, worked=False)
    pace.telling(lambda: False)()  # it found nothing to work on
    assert not pace.due(START + 2 * TICK)
