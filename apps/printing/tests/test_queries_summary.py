"""How printing is going, by function: the printers, the queue and what nobody is there to print."""

import datetime as dt

from django.utils import timezone

from apps.printing.models import PrintJob
from apps.printing.queries.summary import job_summary
from apps.printing.schemas.fields import EmptyIn
from apps.printing.tests.conftest import HUB_DB, age, ctx_for, enqueue, printer, queued_ago, reaches, run

pytestmark = HUB_DB


def test_the_summary_by_function():
    printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    run("printing.settings.update", {"kitchen_printer": "Kitchen"})
    old = enqueue().job
    age(old.id, 4)
    enqueue()
    label = enqueue("barcode_label", {"product_name": "Shampoo", "barcode": "SHA-1", "price": 9.5}).job
    PrintJob.objects.filter(pk=label.id).update(status="failed")
    out = run("printing.job.summary")
    by_usage = {row.usage: row for row in out.usages}
    assert [row.usage for row in out.usages] == ["receipt", "kitchen", "bar", "label"]
    assert (by_usage["receipt"].printers, by_usage["receipt"].pending, by_usage["receipt"].default_printer) == (1, 2, None)
    assert by_usage["receipt"].oldest_pending_at < timezone.now() - dt.timedelta(minutes=3)
    assert (by_usage["kitchen"].printers, by_usage["kitchen"].default_printer, by_usage["kitchen"].pending) == (1, "Kitchen", 0)
    assert (by_usage["label"].printers, by_usage["label"].failed) == (0, 1)
    assert (out.pending, out.failed) == (2, 1)


def test_the_summary_names_the_printer_each_function_prints_on():
    # The card says WHERE a function prints, never only how many printers it has.
    def prints_on() -> dict:
        return {row.usage: row.prints_on for row in job_summary(ctx_for(), EmptyIn()).usages}

    printer("Till 2", address="10.0.0.9")
    printer("till")
    printer("Office", kind="system", address="")
    printer("Bar", usage="bar", address="10.0.0.3", is_active=False)
    # Nothing chosen: the first active receipt printer by name, whatever its case; a function with no active one, none.
    assert prints_on() == {"receipt": "till", "kitchen": None, "bar": None, "label": None}
    run("printing.settings.update", {"receipt_printer": "Till 2"})
    assert prints_on()["receipt"] == "Till 2"
    # The chosen one goes inactive: its function prints on the first active one again.
    run("printing.printer.update", {"printer": "Till 2", "is_active": False})
    run("printing.printer.update", {"printer": "till", "is_active": False})
    # Only the computer's printer is left: receipts come out there (on A4).
    assert prints_on()["receipt"] == "Office"


def test_the_summary_by_function_counts_what_no_device_set_up_here_can_print():
    # The bell's «Nothing is printing “…”» leads to the printers' summary: each function says it too, so the card
    # never says «Ready» while its paper waits for nobody.
    till = printer("Till")
    enqueue()

    def unattended() -> dict:
        return {row.usage: row.unattended for row in run("printing.job.summary").usages}

    assert unattended() == {"receipt": 1, "kitchen": 0, "bar": 0, "label": 0}
    reaches(till, seen=None)
    # «Set one up» is for what no device set up prints: one set up, even off, is no device to set up.
    assert unattended()["receipt"] == 0


def test_the_summary_by_function_counts_what_waited_a_minute_with_its_device_off_as_the_bell():
    # Where the bell's «Nothing is printing “Receipt”» leads, the receipts' card says the device is off, not «Ready».
    till = printer("Till")
    device = reaches(till, seen=dt.timedelta(minutes=5))
    queued_ago(65)
    queued_ago(10, job_key="sale:2")

    def stalled() -> dict:
        return {row.usage: row.stalled for row in run("printing.job.summary").usages}

    assert stalled() == {"receipt": 1, "kitchen": 0, "bar": 0, "label": 0}
    type(device).objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
    assert stalled()["receipt"] == 0


def test_a_job_waiting_without_a_printer_is_only_taken_by_a_device_of_its_own_function():
    # A kitchen order with no kitchen printer waits for one: the device of the receipts never takes it.
    reaches(printer("Till"))
    enqueue(usage="kitchen", job_key="kitchen:1")
    assert PrintJob.objects.get().printer_id is None
    summary = {row.usage: row.unattended for row in run("printing.job.summary").usages}
    assert (summary["receipt"], summary["kitchen"]) == (0, 1)
