"""The X and Z reports through the Hub's print queue (CASH_REGISTER-F16; Printing's PRINTING-F17), against the
real printing app: «Print» puts a ``cash_session_report`` in the queue of the receipt printer, with the
session's figures as the paper shows them. Without Printing in the business, or without an active receipt
printer in it (the paper would wait for ever), nothing is queued and the screen prints through the browser;
a blind count does not print an open session's figures to whoever may not see the expected cash."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import registry

from apps.cash_register.models import Session
from apps.cash_register.tests.conftest import (
    charge,
    ctx_for,
    open_session,
    run,
)
from apps.printing.models import PrintJob

pytestmark = pytest.mark.django_db


def print_report(session, ctx=None):
    return run("cash_register.session.print", {"session_id": str(session.id)}, ctx)


def lines(job: PrintJob) -> list[tuple[str, float]]:
    return [(line["label"], line["amount"]) for line in job.document["transactions"]]


@pytest.fixture
def till(db):
    """The business's receipt printer, made by Printing."""
    return run(
        "printing.printer.create",
        {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"},
    )


@pytest.fixture
def shift(coffee, till):
    """A shift of 100.00 € with a 1.50 € coffee charged in cash and 0.50 € taken out, and a receipt printer."""
    session = open_session(10000)
    charge()
    run(
        "cash_register.movement.add",
        {"type": "out", "amount": 50, "description": "milk"},
    )
    return session


def test_the_z_report_goes_to_the_receipt_printer_with_the_frozen_figures(shift):
    run(
        "cash_register.session.close",
        {"session_id": str(shift.id), "closing_balance": 10090},
    )
    printed = print_report(shift)
    assert (printed.report, printed.queued) == ("z", True)
    job = PrintJob.objects.get(pk=printed.job_id)
    assert (job.document_type, job.usage, job.source_app, job.reference) == (
        "cash_session_report",
        "receipt",
        "cash_register",
        shift.number,
    )
    document = job.document
    assert document["receipt_id"] == f"{shift.number} (Z)"
    assert document["cashier"] == "tester"
    assert (document["opening_balance"], document["closing_balance"]) == (100.0, 101.0)
    assert lines(job) == [
        ("Sales", 1.5),
        ("Cash sales", 1.5),
        ("Card sales", 0.0),
        ("Refunds", 0.0),
        ("Cash in", 0.0),
        ("Cash out", -0.5),
        ("Comps", 0.0),
        ("Expected", 101.0),
        ("Counted", 100.9),
        ("Over/short", -0.1),
    ]


def test_an_open_session_prints_the_x_report_without_count_or_over_short(shift):
    printed = print_report(shift)
    assert (printed.report, printed.queued) == ("x", True)
    job = PrintJob.objects.get(pk=printed.job_id)
    assert job.document["receipt_id"] == f"{shift.number} (X)"
    assert job.document["closing_balance"] == 101.0
    labels = [label for label, _ in lines(job)]
    assert "Expected" in labels
    assert "Counted" not in labels and "Over/short" not in labels


def test_a_session_closed_by_itself_says_so_and_has_no_count(shift):
    Session.objects.filter(pk=shift.id).update(
        opened_at=timezone.now() - dt.timedelta(days=2)
    )
    run("cash_register.settings.update", {"auto_close_enabled": True})
    assert len(run("cash_register.session.auto_close").closed) == 1
    job = PrintJob.objects.get(pk=print_report(shift).job_id)
    assert job.document["cashier"] == "Closed by itself"
    assert "Counted" not in [label for label, _ in lines(job)]


def test_other_payment_methods_are_a_line_only_when_there_were_some(shift):
    run("sale.payment_method.create", {"name": "Bizum", "type": "other"})
    charge(payments=[{"method": "Bizum"}])
    labels = [label for label, _ in lines(PrintJob.objects.get(pk=print_report(shift).job_id))]
    assert "Sales with other payment methods" in labels


def test_every_print_is_a_paper_of_its_own(shift):
    first, second = print_report(shift), print_report(shift)
    assert first.job_id != second.job_id
    assert PrintJob.objects.filter(source_app="cash_register").count() == 2


def test_without_an_active_receipt_printer_nothing_is_queued_and_the_screen_prints(shift, till):
    run("printing.printer.update", {"printer": str(till.id), "is_active": False})
    printed = print_report(shift)
    assert (printed.queued, printed.job_id) == (False, None)
    assert not PrintJob.objects.exists()
    run(
        "printing.printer.create",
        {"name": "Bar", "kind": "network", "address": "192.168.1.51", "usage": "kitchen"},
    )
    assert print_report(shift).queued is False


def test_the_receipt_printer_named_is_said(shift):
    run("printing.settings.update", {"receipt_printer": "Till"})
    assert print_report(shift).printer == "Till"


def test_without_printing_in_the_business_nothing_is_queued_and_the_screen_prints(shift, monkeypatch):
    # Not installed or off in this business: its operation is not there (the same path as app_inactive).
    monkeypatch.delitem(registry, "printing.job.create")
    printed = print_report(shift)
    assert (printed.report, printed.queued, printed.job_id) == ("x", False, None)
    assert not PrintJob.objects.exists()


def test_a_blind_count_keeps_the_open_report_from_whoever_may_not_see_the_expected(shift):
    run("cash_register.settings.update", {"require_blind_count": True})
    with pytest.raises(Conflict) as refused:
        print_report(shift, ctx_for("hub_employee"))
    assert refused.value.code == "cash_register.report_hidden"
    assert not PrintJob.objects.exists()
    assert print_report(shift, ctx_for("hub_manager")).queued is True


def test_a_blind_count_does_not_keep_a_closed_report(shift):
    run("cash_register.settings.update", {"require_blind_count": True})
    run(
        "cash_register.session.close",
        {"session_id": str(shift.id), "closing_balance": 10100},
    )
    assert print_report(shift, ctx_for("hub_employee")).queued is True


def test_whoever_may_not_print_is_refused_by_printing(shift):
    ctx = ctx_for("hub_employee")
    ctx = type(ctx)(
        scope=ctx.scope,
        actor=ctx.actor,
        permissions=ctx.permissions - {"printing.print"},
    )
    with pytest.raises(PermissionDenied):
        print_report(shift, ctx)
    assert not PrintJob.objects.exists()


def test_an_unknown_session_is_not_found(db):
    with pytest.raises(NotFound):
        run(
            "cash_register.session.print",
            {"session_id": "019a0000-0000-7000-8000-000000000000"},
        )


def test_the_paper_speaks_the_language_of_whoever_prints(shift):
    job = PrintJob.objects.get(pk=print_report(shift, ctx_for(language="es")).job_id)
    assert job.document["locale"] == "es"
    assert [label for label, _ in lines(job)][:3] == [
        "Ventas",
        "Ventas en efectivo",
        "Ventas con tarjeta",
    ]
