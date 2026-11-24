"""How long the queue keeps a job (PRINTING-F20)."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import PermissionDenied
from live.context import system_context

from apps.printing.models import PrintJob
from apps.printing import services
from apps.printing.tests.conftest import A, HUB_DB, ctx_for, enqueue, printer, run
from apps.printing.tests.test_services import events

pytestmark = HUB_DB


# ── PRINTING-F20 How long the queue keeps a job ─────────────────────────────────────────────────────


def ended(days: int, status: str, **more) -> PrintJob:
    """A job of the queue that ended ``days`` ago in ``status`` (or, still waiting, was queued then)."""
    when = timezone.now() - dt.timedelta(days=days)
    queued = PrintJob.objects.get(pk=enqueue(source_ref=f"{status}-{days}").job.id)
    stamp = {"done": "printed_at", "cancelled": "cancelled_at", "failed": "failed_at"}.get(status)
    PrintJob.objects.filter(pk=queued.pk).update(status=status, created_at=when - dt.timedelta(minutes=5), **({stamp: when} if stamp else {}), **more)
    return queued


def prune(ctx=None):
    return run("printing.job.prune", {}, ctx or system_context(A))


def test_a_finished_job_is_forgotten_30_days_after_it_ended_and_a_waiting_one_never():
    printer("Till")
    gone = [ended(31, "done"), ended(31, "cancelled"), ended(31, "failed")]
    kept = [ended(29, "done"), ended(29, "failed"), ended(60, "pending"), ended(60, "sent")]
    out = prune()
    assert out.count == 3
    assert set(PrintJob.objects.values_list("pk", flat=True)) == {job.pk for job in kept}
    assert not PrintJob.objects.filter(pk__in=[job.pk for job in gone]).exists()
    # The screens that show the queue re-run: a deleted failed job no longer counts.
    assert events("printing.job.pruned") == [{"count": 3}]


def test_nothing_to_forget_is_no_event():
    printer("Till")
    ended(10, "done")
    assert prune().count == 0
    assert events("printing.job.pruned") == []


def test_the_queue_is_forgotten_in_batches(monkeypatch):
    printer("Till")
    for _ in range(3):
        ended(40, "done")
    monkeypatch.setattr(services.prune, "PRUNE_BATCH", 2)
    assert [prune().count, prune().count, prune().count] == [2, 1, 0]


def test_a_forgotten_key_can_print_again():
    printer("Till")
    old = ended(40, "done")
    prune()
    again = enqueue(job_key=old.job_key)
    assert (again.duplicate, again.job.status) == (False, "pending")


def test_only_the_platform_forgets_the_queue():
    for role in ("hub_manager", "hub_employee"):
        with pytest.raises(PermissionDenied):
            prune(ctx_for(role))
