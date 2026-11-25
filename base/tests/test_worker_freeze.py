"""The worker's freeze switch (``control.freeze.set``, hub#930).

While a database upgrade runs nothing may change a schema: frozen, the worker makes, drops and moves no database, sets
up no app's tables and does no data work, while the relay, every hub's tasks and the nightly measure go on; once lifted,
the next tick makes what waited. It reads the switch once a pass and says once when it freezes and once when it is
lifted; a switch it cannot read freezes the tick. No database but for the switch's real read: the passes of the tick
are the fakes of ``test_worker.py``; the switch itself is ``control/tests/test_freeze.py``'s.
"""

import logging
import threading

import pytest
from django.db import DatabaseError

from base import worker
from base.tests.test_worker import (
    TICK,
    activations_pass,
    calls,
    clock,
    data_pass,
    due,
    every_pass,
    freeze_switch,
    hubs_pass,
    inline_passes,
    moves_pass,
    nobody_without_a_database,
    outbox,
    reaper,
    stop_after,
    stopped,
    tasks,
    ten,
    usage_pass,
)

# The fakes of every pass of the tick, autouse, and the fixtures the tests ask for.
__all__ = [
    "activations_pass",
    "calls",
    "data_pass",
    "due",
    "freeze_switch",
    "hubs_pass",
    "inline_passes",
    "moves_pass",
    "nobody_without_a_database",
    "outbox",
    "reaper",
    "tasks",
    "usage_pass",
]


def ticks(count: int, **options) -> int:
    """Run the loop for ``count`` ticks, at 10:00, 10:01…; its exit code."""
    stop = threading.Event()
    wait, _ = stop_after(stop, count)
    return worker.run(stop, tick_seconds=TICK, wait=wait, clock=clock(*range(count)), **options)


def test_frozen_it_makes_drops_moves_and_sets_up_nothing_while_the_relay_the_tasks_and_the_use_go_on(
    monkeypatch, calls, tasks, due, outbox, moves_pass, reaper, freeze_switch
):
    """While a database upgrade runs nothing may change a schema: no sign-up or demo made, no demo dropped, no app's
    tables made, no move, no data work (a business past its days is dropped); the relay, every hub's tasks (VeriFactu's
    queue among them) and the nightly measure go on."""
    freeze_switch.answers = [True]
    order: list[str] = []
    every_pass(monkeypatch, order, due, outbox)

    assert ticks(2) == 0

    assert order == ["relay", "hubs", "usage"] * 2
    assert (due.passes, moves_pass, reaper.passes) == ([], [], [])


def test_the_switch_is_read_once_a_pass(calls, freeze_switch):
    ticks(3)

    assert freeze_switch.reads == 3


def test_a_stop_before_the_first_tick_reads_no_switch(calls, freeze_switch):
    worker.run(stopped())

    assert freeze_switch.reads == 0


def test_once_lifted_the_next_tick_makes_what_waited_and_reaps_at_once(
    monkeypatch, calls, tasks, due, outbox, moves_pass, reaper, freeze_switch
):
    freeze_switch.answers = [True, True, False]
    order: list[str] = []
    every_pass(monkeypatch, order, due, outbox)

    ticks(3)

    assert order[-6:] == ["relay", "hubs", "activations", "data", "usage", "due"]
    # The reaper, held while frozen, runs on the first tick after: the demos that ended do not wait another minute.
    assert (due.passes, moves_pass, reaper.passes) == ([ten(2)], [ten(2)], [ten(2)])


def test_frozen_the_e2es_worker_does_nothing(monkeypatch, calls, tasks, due, outbox, reaper, freeze_switch):
    freeze_switch.answers = [True]
    order: list[str] = []
    every_pass(monkeypatch, order, due, outbox)

    ticks(2, databases_only=True)

    assert (order, reaper.passes) == ([], [])


def test_it_says_once_when_it_freezes_and_once_when_it_is_lifted(caplog, calls, freeze_switch):
    freeze_switch.answers = [False, True, True, False, False]

    with caplog.at_level(logging.INFO, logger="base.worker"):
        ticks(5)

    said = [r.getMessage() for r in caplog.records if r.name == "base.worker" and "freeze" in r.getMessage()]
    assert len(said) == 2
    assert "frozen" in said[0] and "control.freeze.set" in said[0]
    assert "lifted" in said[1]


@pytest.mark.django_db
def test_the_switch_read_says_whether_control_is_frozen(monkeypatch):
    from control import services as control_services
    from control.schemas import FreezeIn
    from live.context import system_context

    from base.registry import REGISTRY_SCOPE

    monkeypatch.undo()
    platform = system_context(REGISTRY_SCOPE)

    assert worker._frozen() is False
    control_services.freeze.freeze_set(platform, FreezeIn(frozen=True, reason="upgrade"))
    assert worker._frozen() is True
    control_services.freeze.freeze_set(platform, FreezeIn(frozen=False))
    assert worker._frozen() is False


def test_the_switch_that_cannot_be_read_freezes_the_tick_and_says_why(monkeypatch, caplog):
    from control import queries as control_queries

    monkeypatch.undo()
    failure = DatabaseError("server closed the connection unexpectedly")

    def broken():
        raise failure

    monkeypatch.setattr(control_queries, "active_freeze", broken)

    with caplog.at_level(logging.ERROR, logger="base.worker"):
        assert worker._frozen() is True

    [record] = [r for r in caplog.records if r.name == "base.worker"]
    assert "freeze" in record.getMessage() and record.exc_info[1] is failure
