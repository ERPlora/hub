"""The X and Z reports through the Hub's print queue (CASH_REGISTER-F16; Printing's PRINTING-F17), against the
real printing app: «Print» puts a ``cash_session_report`` in the queue of the receipt printer, with the
session's figures as the paper shows them. Without Printing in the business, or without an active receipt
printer in it (the paper would wait for ever), nothing is queued and the print fails with why: the screen prints
through the browser, and the assistant's receipt says it was not done. A blind count does not print an open
session's figures to whoever may not see the expected cash."""

import dataclasses
import datetime as dt

import pytest
from django.test import RequestFactory
from django.utils import timezone
from live.errors import AppInactive, Conflict, NotFound, PermissionDenied
from live.operations import registry

from apps.cash_register.models import Session
from apps.cash_register.tests.conftest import (
    HUB_DB,
    charge,
    ctx_for,
    open_session,
    run,
    void,
)
from apps.printing.models import PrintJob
from apps.sale.tests.conftest import confirmed_by_the_assistant

pytestmark = HUB_DB


def print_report(session, ctx=None):
    return run("cash_register.session.print", {"session_id": str(session.id)}, ctx)


def not_printed(session, ctx=None) -> str:
    """The code ``cash_register.session.print`` fails with; nothing is queued."""
    with pytest.raises(Conflict) as failed:
        print_report(session, ctx)
    assert not PrintJob.objects.exists()
    return failed.value.code


def lines(job: PrintJob) -> list[tuple[str, float]]:
    return [(line["label"], line["amount"]) for line in job.document["transactions"]]


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
    assert printed.model_dump() == {"report": "z", "job_id": printed.job_id, "printer": "Till"}
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
    assert printed.report == "x"
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


def test_a_sale_voided_in_the_same_shift_is_on_the_paper_neither_as_a_sale_nor_as_a_refund(shift):
    void(charge(payments=[{"method": "card"}]))
    printed = dict(lines(PrintJob.objects.get(pk=print_report(shift).job_id)))
    assert [printed[label] for label in ("Sales", "Card sales", "Refunds", "Expected")] == [1.5, 0.0, 0.0, 101.0]


def test_every_print_is_a_paper_of_its_own(shift):
    first, second = print_report(shift), print_report(shift)
    assert first.job_id != second.job_id
    assert PrintJob.objects.filter(source_app="cash_register").count() == 2


def test_without_an_active_receipt_printer_it_is_not_printed(shift, till):
    run("printing.printer.update", {"printer": str(till.id), "is_active": False})
    assert not_printed(shift) == "cash_register.no_printer"
    run(
        "printing.printer.create",
        {"name": "Bar", "kind": "network", "address": "192.168.1.51", "usage": "kitchen"},
    )
    assert not_printed(shift) == "cash_register.no_printer"


def test_the_receipt_printer_named_is_said(shift):
    run("printing.settings.update", {"receipt_printer": "Till"})
    assert print_report(shift).printer == "Till"


def test_with_two_tills_the_report_comes_out_at_the_till_that_prints_it(shift, till):
    """PRINTING-F22: the terrace's till prints its shift report on its own receipt printer, not the business's."""
    terrace = run(
        "printing.printer.create",
        {"name": "Till 2", "kind": "network", "address": "192.168.1.51", "usage": "receipt"},
    )
    at_the_terrace = dataclasses.replace(ctx_for("hub_manager"), request=RequestFactory().post("/", HTTP_X_DEVICE_ID="terrace"))
    run("printing.device.register", {"name": "Terrace", "printers": [str(terrace.id)]}, at_the_terrace)
    out = print_report(shift, at_the_terrace)
    assert out.printer == "Till 2"
    assert PrintJob.objects.get(pk=out.job_id).printer_id == terrace.id


def test_without_printing_in_the_business_it_is_not_printed(shift, monkeypatch):
    # Not installed or off in this business: its operation is not there (the same path as app_inactive).
    monkeypatch.delitem(registry, "printing.job.create")
    assert not_printed(shift) == "cash_register.no_printer"


def test_with_printing_off_it_is_not_printed(shift, monkeypatch):
    def off(ctx, data):
        raise AppInactive("Printing is off.")

    summary = registry["printing.job.summary"]
    monkeypatch.setitem(registry, "printing.job.summary", dataclasses.replace(summary, fn=off))
    assert not_printed(shift) == "cash_register.no_printer"


# ── From the assistant (BASE-F97, BASE-F99) ───────────────────────────────────────────────────────────────────────────
# hub#2328: with no receipt printer, the receipt under the answer said «Done» and nothing was printed.


@pytest.mark.parametrize(
    ("language", "said"),
    [
        ("es", "Ninguna impresora de recibos recibe este informe: abre la sesión para imprimirlo en este dispositivo."),
        ("en", "No receipt printer takes this report: open the session to print it on this device."),
    ],
)
def test_from_the_assistant_a_report_no_printer_takes_is_not_done_and_says_why(shift, till, language, said):
    run("printing.printer.update", {"printer": str(till.id), "is_active": False})
    row = confirmed_by_the_assistant("cash_register.session.print", {"session_id": str(shift.id)}, ctx_for(language=language))
    assert (row["outcome"], row["code"], row["reason"]) == ("error", "cash_register.no_printer", {language: said})
    assert not PrintJob.objects.exists()


def test_from_the_assistant_a_report_the_receipt_printer_took_is_done(shift):
    row = confirmed_by_the_assistant("cash_register.session.print", {"session_id": str(shift.id)}, ctx_for(language="es"))
    assert (row["outcome"], row["code"], row["reason"]) == ("ok", "", {})
    assert PrintJob.objects.filter(source_app="cash_register").count() == 1


def test_a_blind_count_keeps_the_open_report_from_whoever_may_not_see_the_expected(shift):
    run("cash_register.settings.update", {"require_blind_count": True})
    with pytest.raises(Conflict) as refused:
        print_report(shift, ctx_for("hub_employee"))
    assert refused.value.code == "cash_register.report_hidden"
    assert not PrintJob.objects.exists()
    assert print_report(shift, ctx_for("hub_manager")).job_id is not None


def test_a_blind_count_does_not_keep_a_closed_report(shift):
    run("cash_register.settings.update", {"require_blind_count": True})
    run(
        "cash_register.session.close",
        {"session_id": str(shift.id), "closing_balance": 10100},
    )
    assert print_report(shift, ctx_for("hub_employee")).job_id is not None


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


def test_the_z_says_when_the_session_closed_and_the_x_when_it_is_printed(shift, monkeypatch, in_business_a):
    """The device printed its own hour on the report: the paper brings the hour of what it reports, on the
    business's clock. At 23:30 of the 2nd in Bogotá it is already the 3rd in Madrid."""
    monkeypatch.setattr(in_business_a, "timezone", "America/Bogota")
    night = dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.UTC)
    with monkeypatch.context() as clock:
        clock.setattr(timezone, "now", lambda: night)
        assert PrintJob.objects.get(pk=print_report(shift).job_id).document["date"] == "02/11/2026 23:30"
    run("cash_register.session.close", {"session_id": str(shift.id), "closing_balance": 10090})
    Session.objects.filter(pk=shift.id).update(closed_at=night)
    assert PrintJob.objects.get(pk=print_report(shift).job_id).document["date"] == "02/11/2026 23:30"
