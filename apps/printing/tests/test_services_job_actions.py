"""Retrying and cancelling a job (PRINTING-F14)."""

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.printing.models import Printer, PrintJob
from apps.printing.tests.conftest import HUB_DB, ctx_for, enqueue, printer, run
from apps.printing.tests.test_services import claim, done, events, expire

pytestmark = HUB_DB


# ── PRINTING-F14 Retry and cancel ───────────────────────────────────────────────────────────────


def failed_job(till: Printer) -> PrintJob:
    queued = enqueue().job
    PrintJob.objects.filter(pk=queued.id).update(status="failed", attempts=5, last_error="out of paper")
    return PrintJob.objects.get(pk=queued.id)


def test_a_failed_job_goes_back_to_the_queue_with_no_attempts():
    till = printer("Till")
    failed = failed_job(till)
    out = run("printing.job.retry", {"job_id": str(failed.id)}, ctx_for(actor="Ana"))
    assert (out.status, out.attempts, out.retried_by) == ("pending", 0, "Ana")
    assert out.retried_at is not None
    assert events("printing.job.retried") == [{"id": str(failed.id)}]
    assert events("printing.job.queued")[-1]["id"] == str(failed.id)


def test_a_retry_goes_to_the_printer_that_prints_its_function_now():
    till = printer("Till")
    failed = failed_job(till)
    PrintJob.objects.filter(pk=failed.id).update(printer_id=till.id)
    Printer.objects.filter(pk=till.id).update(is_active=False)
    new = printer("New till", address="10.0.0.5")
    assert run("printing.job.retry", {"job_id": str(failed.id)}).printer_id == new.id


def test_a_queued_failed_or_unanswered_job_is_retried_and_nothing_else():
    till = printer("Till")
    queued = enqueue(source_ref="T-7").job
    assert run("printing.job.retry", {"reference": "T-7"}).status == "pending"
    claim(till)
    with pytest.raises(Conflict) as refused:
        run("printing.job.retry", {"reference": "T-7"})
    assert refused.value.code == "printing.job_not_retryable"
    assert refused.value.message == (
        "Only a queued or failed job, or a sent one with no answer, goes back to the queue; this one is sent."
    )
    expire(queued.id)
    assert run("printing.job.retry", {"reference": "T-7"}).status == "pending"


def test_a_job_is_cancelled_with_its_reason_stays_and_lets_its_document_go():
    printer("Till")
    queued = enqueue(source_ref="T-8").job
    out = run("printing.job.cancel", {"reference": "T-8", "reason": "customer left"}, ctx_for(actor="Ana"))
    assert (out.status, out.cancelled_by, out.cancel_reason) == ("cancelled", "Ana", "customer left")
    cancelled = PrintJob.objects.get(pk=queued.id)
    assert (cancelled.document, cancelled.html, cancelled.reference) == ({}, "", "T-8")
    assert events("printing.job.cancelled") == [{"id": str(queued.id)}]


def test_a_job_a_device_is_printing_or_printed_is_not_cancelled():
    till = printer("Till")
    queued = enqueue().job
    claim(till)
    with pytest.raises(Conflict) as refused:
        run("printing.job.cancel", {"job_id": str(queued.id)})
    assert refused.value.code == "printing.job_not_cancellable"
    done(queued.id)
    with pytest.raises(Conflict) as refused:
        run("printing.job.cancel", {"job_id": str(queued.id)})
    assert refused.value.message == "A job that is printing or has printed is not cancelled; this one is printed."


def test_the_newest_job_of_a_reference_is_the_one_named():
    printer("Till")
    enqueue(source_ref="T-9")
    newest = enqueue(source_ref="T-9").job
    assert run("printing.job.cancel", {"reference": "T-9"}).id == newest.id
    with pytest.raises(NotFound) as refused:
        run("printing.job.cancel", {"reference": "T-404"})
    assert refused.value.message == "There is no print job with that id or number."


@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_only_who_runs_the_business_retries_and_cancels(role):
    printer("Till")
    queued = enqueue().job
    with pytest.raises(PermissionDenied):
        run("printing.job.cancel", {"job_id": str(queued.id)}, ctx_for(role))
    with pytest.raises(PermissionDenied):
        run("printing.job.retry", {"job_id": str(queued.id)}, ctx_for(role))
