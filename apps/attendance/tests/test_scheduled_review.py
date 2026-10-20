"""ATTENDANCE-F05 as the worker runs it: ``attendance.review_stale`` through ``base.scheduler`` every quarter
of an hour, as the system on the worker's scope (phase 1: one scope, the days are shared). A forgotten day
is flagged with its event before anybody clocks in again; the next pass, with nothing new, flags nothing.
"""

import datetime as dt

import pytest
from live.models import OutboxEvent

from apps.attendance import events
from apps.attendance.models import Record
from base import scheduler

from .conftest import utc

pytestmark = pytest.mark.django_db

TASK = "attendance.review_stale"


@pytest.fixture
def worker(settings, monkeypatch, clock):
    """The worker's scope and attendance's task, scheduled as the worker does at 20:01 UTC."""
    settings.WORKER_SCOPE_SLUG = "a"
    # Inside the test's transaction a released connection could not be opened again.
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: None)
    started = clock("2026-10-06T20:01")
    scheduler.sync(started, declared=[task for task in scheduler.tasks() if task.app_label == "attendance"])
    return started


def flagged() -> list[dict]:
    return list(OutboxEvent.objects.filter(name=events.RECORD_FLAGGED).values_list("payload", flat=True))


def test_the_worker_flags_a_forgotten_day_every_quarter_of_an_hour(worker, person, clock):
    ana, _ = person()
    old = Record.objects.create(member=ana, clock_in_at=utc("2026-10-06T07:00"), work_date=dt.date(2026, 10, 6))
    due = utc("2026-10-06T20:15")
    assert scheduler.next_after("*/15 * * * *", worker) == due

    # Not before its quarter of an hour.
    assert scheduler.run_due(due - dt.timedelta(seconds=30)) == []
    old.refresh_from_db()
    assert old.status == Record.Status.OPEN

    clock(due)
    assert scheduler.run_due(due) == [TASK]
    old.refresh_from_db()
    assert old.status == Record.Status.NEEDS_REVIEW
    assert old.clock_out_at is None
    assert flagged() == [{"id": str(old.id), "member_id": str(ana.id)}]

    # The next quarter runs again and, with nothing new, says nothing.
    later = due + dt.timedelta(minutes=15)
    clock(later)
    assert scheduler.run_due(later) == [TASK]
    assert len(flagged()) == 1
