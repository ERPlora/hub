"""The printers (PRINTING-F03, F04, F19): the list, one of them, its state and how it is doing."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import NotFound

from apps.printing.models import Printer, PrintJob
from apps.printing.queries.printers import get_printer
from apps.printing.schemas import PrinterRefIn
from apps.printing.tests.conftest import HUB_DB, age, ctx_for, enqueue, printer, run

pytestmark = HUB_DB


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
    assert get_printer(ctx_for(), PrinterRefIn(printer="TILL")).id == till.id
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
