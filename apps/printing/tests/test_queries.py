"""Read operations of the printing app: the settings (the factory ones until saved), the printers with
their state, the state of one printer, the queue and its summary by function."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import NotFound, PermissionDenied

from apps.printing.models import Printer, PrintJob
from apps.printing.tests.conftest import ctx_for, enqueue, printer, run

pytestmark = pytest.mark.django_db

ITEM = {"name": "Haircut", "quantity": 1, "total": 18.0}


def age(job_id, minutes: int) -> None:
    PrintJob.objects.filter(pk=job_id).update(created_at=timezone.now() - dt.timedelta(minutes=minutes))


# ── Settings ────────────────────────────────────────────────────────────────────────────────────


def test_a_business_that_never_saved_has_the_factory_settings():
    # printing#42: the read answers the defaults and never writes a row.
    out = run("printing.settings.get")
    assert (out.print_receipt_on_sale, out.open_drawer_on_sale, out.receipt_copies, out.updated_at) == (True, False, 1, None)
    assert (out.receipt_printer_id, out.kitchen_printer_id, out.bar_printer_id, out.label_printer_id) == (None,) * 4
    from apps.printing.models import Settings

    assert not Settings.objects.exists()


def test_the_settings_read_what_was_saved():
    kitchen = printer("Kitchen", usage="kitchen")
    run("printing.settings.update", {"print_receipt_on_sale": False, "kitchen_printer": "Kitchen"})
    out = run("printing.settings.get", ctx=ctx_for("hub_employee"))
    assert (out.print_receipt_on_sale, out.kitchen_printer_id) == (False, kitchen.id)


def test_a_role_without_printing_reads_nothing():
    with pytest.raises(PermissionDenied):
        run("printing.settings.get", ctx=ctx_for("nobody"))


# ── Printers (PRINTING-F03, F04, F19) ───────────────────────────────────────────────────────────


def test_the_printers_by_name_with_search_and_filters():
    printer("Till")
    printer("Kitchen", usage="kitchen", address="10.0.0.2")
    printer("Office", kind="system", address="", is_active=False)
    page = run("printing.printer.list")
    assert [row.name for row in page.rows] == ["Kitchen", "Office", "Till"]
    assert (page.total, page.limit, page.offset) == (3, 50, 0)
    assert [row.name for row in run("printing.printer.list", {"search": "10.0.0"}).rows] == ["Kitchen"]
    assert [row.name for row in run("printing.printer.list", {"usage": "kitchen"}).rows] == ["Kitchen"]
    assert [row.name for row in run("printing.printer.list", {"kind": "system"}).rows] == ["Office"]
    assert [row.name for row in run("printing.printer.list", {"is_active": True}).rows] == ["Kitchen", "Till"]
    assert [row.name for row in run("printing.printer.list", {"sort": "name", "dir": "desc", "limit": 1}).rows] == ["Till"]


def test_a_printer_by_its_name_or_its_id():
    till = printer("Till")
    assert run("printing.printer.get", {"printer": "TILL"}).id == till.id
    assert run("printing.printer.get", {"printer_id": str(till.id)}).name == "Till"
    assert run("printing.printer.get", {"printer": str(till.id)}).name == "Till"
    with pytest.raises(NotFound):
        run("printing.printer.get", {"printer": "Nowhere"})


def test_the_state_of_a_printer():
    till = printer("Till")
    assert run("printing.printer.get", {"printer": "Till"}).state == "ready"
    queued = enqueue().job
    assert run("printing.printer.get", {"printer": "Till"}).pending == 1
    assert run("printing.printer.get", {"printer": "Till"}).state == "ready"
    age(queued.id, 2)
    assert run("printing.printer.get", {"printer": "Till"}).state == "waiting"
    now = timezone.now()
    Printer.objects.filter(pk=till.id).update(last_failed_at=now, last_error="out of paper")
    out = run("printing.printer.get", {"printer": "Till"})
    assert (out.state, out.last_error) == ("failing", "out of paper")
    Printer.objects.filter(pk=till.id).update(last_printed_at=now + dt.timedelta(seconds=1))
    assert run("printing.printer.get", {"printer": "Till"}).state == "waiting"
    Printer.objects.filter(pk=till.id).update(is_active=False)
    assert run("printing.printer.get", {"printer": "Till"}).state == "inactive"


def test_the_status_of_a_printer_counts_its_queue():
    printer("Till")
    run("printing.settings.update", {"receipt_printer": "Till"})
    first = enqueue().job
    age(first.id, 3)
    second = enqueue().job
    PrintJob.objects.filter(pk=second.id).update(status="failed")
    out = run("printing.printer.status", {"printer": "till"}, ctx_for("hub_employee"))
    assert (out.printer.name, out.is_default, out.pending, out.sent, out.failed) == ("Till", True, 1, 0, 1)
    assert out.oldest_pending_at < timezone.now() - dt.timedelta(minutes=2)


# ── The queue (PRINTING-F01, F14) ───────────────────────────────────────────────────────────────


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
    # hub#1527: the card says WHERE a function prints, never only how many printers it has.
    def prints_on() -> dict:
        return {row.usage: row.prints_on for row in run("printing.job.summary").usages}

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
