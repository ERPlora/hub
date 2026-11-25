"""The print queue (PRINTING-F01, F14): the list with its filters, and one job as the queue titles it."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import NotFound, PermissionDenied

from apps.printing.models import PrintJob
from apps.printing.queries.jobs import get_job
from apps.printing.schemas.jobs import JobRefIn
from apps.printing.tests.conftest import HUB_DB, age, ctx_for, enqueue, printer, run

pytestmark = HUB_DB

ITEM = {"name": "Haircut", "quantity": 1, "total": 18.0}


def test_the_queue_newest_first_with_its_printer_and_what_can_be_done():
    printer("Till")
    first = enqueue(source_ref="T-1").job
    age(first.id, 5)
    second = enqueue(source_ref="T-2").job
    PrintJob.objects.filter(pk=first.id).update(status="failed", attempts=5, last_error="out of paper")
    page = run("printing.job.list")
    assert [row.reference for row in page.rows] == ["T-2", "T-1"]
    newest, oldest = page.rows
    assert (newest.printer_name, newest.status, newest.retryable, newest.cancellable, newest.stale) == (
        "Till",
        "pending",
        True,
        True,
        False,
    )
    assert (oldest.status, oldest.retryable, oldest.cancellable, oldest.last_error) == ("failed", True, True, "out of paper")
    assert second.id == newest.id


@pytest.mark.parametrize(("language", "title"), [("es", "Comanda de cocina M-12"), ("en", "Kitchen order M-12")])
def test_a_job_by_its_id_or_its_number_titled_as_the_queue_titles_it(language, title):
    """«printing.job.get»: one job as the queue shows it, titled by its document and its number in the reader's
    language — what the assistant's card names a job by."""
    printer("Kitchen", usage="kitchen")
    queued = enqueue("kitchen_order", {"order_number": "M-12", "items": [ITEM]}).job
    by_id = run("printing.job.get", {"job_id": str(queued.id)}, ctx_for("hub_employee", language=language))
    assert (by_id.id, by_id.reference, by_id.document_type, by_id.status, by_id.label) == (
        queued.id,
        "M-12",
        "kitchen_order",
        "pending",
        title,
    )
    assert run("printing.job.get", {"reference": "m-12"}, ctx_for(language=language)).id == queued.id


def test_a_job_with_no_number_is_titled_by_what_it_is():
    till = printer("Till")
    page = run("printing.printer.test", {"printer_id": str(till.id)})
    opening = PrintJob.objects.create(job_key="drawer-1", kind=PrintJob.Kind.DRAWER, usage="receipt", printer_id=till.id)
    untitled = enqueue("generic", {"lines": ["Hello"]}).job
    titles = [get_job(ctx_for(), JobRefIn(job_id=job)).label for job in (page.id, opening.id, untitled.id)]
    assert titles == ["Test page Till", "Open the drawer", "Document"]


def test_a_job_that_is_not_there_or_for_nobody_with_printing_is_never_read():
    with pytest.raises(NotFound) as missing:
        run("printing.job.get", {"job_id": "0192f0b2-0000-7000-8000-000000000000"})
    assert missing.value.code == "printing.job_not_found"
    queued = enqueue().job
    with pytest.raises(PermissionDenied):
        run("printing.job.get", {"job_id": str(queued.id)}, ctx_for("nobody"))


def test_a_sent_job_with_no_answer_is_stale():
    printer("Till")
    queued = enqueue().job
    PrintJob.objects.filter(pk=queued.id).update(status="sent", leased_until=timezone.now() - dt.timedelta(seconds=1))
    row = run("printing.job.list").rows[0]
    assert (row.status, row.stale, row.retryable, row.cancellable) == ("sent", True, True, True)
    PrintJob.objects.filter(pk=queued.id).update(leased_until=timezone.now() + dt.timedelta(seconds=60))
    row = run("printing.job.list").rows[0]
    assert (row.stale, row.retryable, row.cancellable) == (False, False, False)


def test_the_queue_filters():
    till = printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    enqueue(source_ref="T-1")
    kitchen = enqueue("kitchen_order", {"items": [ITEM], "order_number": 7}).job
    PrintJob.objects.filter(pk=kitchen.id).update(status="done")
    assert [row.reference for row in run("printing.job.list", {"usage": "kitchen"}).rows] == ["7"]
    assert [row.reference for row in run("printing.job.list", {"status": "pending"}).rows] == ["T-1"]
    assert [row.reference for row in run("printing.job.list", {"printer_id": str(till.id)}).rows] == ["T-1"]
    assert [row.reference for row in run("printing.job.list", {"search": "t-1"}).rows] == ["T-1"]
    assert [row.reference for row in run("printing.job.list", {"sort": "usage", "dir": "asc"}).rows] == ["7", "T-1"]
