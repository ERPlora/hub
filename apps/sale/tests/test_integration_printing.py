"""Sales asks Printing for its paper by name (PRINTING-F07, F08, F09, F13; SALE-F21, F29; PLAN-HUB «El cobro y la
comanda llaman a la cola dentro de su propia transacción»): the receipt at checkout inside the charge's own
transaction, a reprint marked as a copy and the bill of a check. No mocks: Inventory owns the products,
Invoicing numbers the ticket and VeriFactu seals it, Printing queues the paper. Without Printing on, without a
printer that takes the paper or with a fiscal document still pending, nothing is queued and the screen prints
it; a refusal of Printing never spoils the charge.
"""

import dataclasses

import pytest
from live.operations import registry

from apps.printing.models import PrintJob
from apps.sale.models import Sale
from apps.sale.tests.conftest import ctx_for, run

pytestmark = pytest.mark.django_db

ISSUER = {
    "legal_name": "Bar Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}
CASH = [{"method": "cash", "tendered": 500}]


@pytest.fixture
def issuer(db):
    return run("invoice.issuer.update", ISSUER)


@pytest.fixture
def bar(product, issuer):
    product("Coffee", "COF", 150, "restaurant.drink")
    run("sale.settings.update", {"receipt_header": "Bar Ana\nCalle Mayor 1", "receipt_footer": "Thank you!"})


@pytest.fixture
def till(db):
    return run(
        "printing.printer.create", {"name": "Till", "kind": "network", "address": "192.168.1.50", "usage": "receipt"}
    )


def charge(key="sale-print-1", payments=None, ctx=None, **more):
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "lines": [{"product": "COF", "quantity": "2"}],
            "payments": payments or [{"method": "card"}],
            **more,
        },
        ctx,
    )


def jobs() -> list[PrintJob]:
    return list(PrintJob.objects.select_related("printer").order_by("created_at", "id"))


def test_the_receipt_prints_at_checkout_inside_the_charge(bar, till):
    out = charge()
    (job,) = jobs()
    assert out.printed.model_dump() == {"queued": True, "job_id": job.id, "printer": "Till"}
    assert (job.document_type, job.source_app, job.reference, job.job_key, job.printer.name) == (
        "receipt",
        "sale",
        out.invoice_number,
        f"sale-{out.id}-receipt",
        "Till",
    )
    paper = job.document
    assert (paper["business_name"], paper["receipt_id"], paper["duplicate"], paper["total"]) == (
        "Bar Ana",
        out.invoice_number,
        False,
        3.0,
    )
    # Sealed by VeriFactu in the same commit: the QR opens the paper, as on screen.
    assert paper["qr_data"].startswith("https://") and paper["qr_heading"] == "QR tributario:"


def test_the_drawer_opens_when_cash_comes_in(bar, till):
    run("printing.settings.update", {"open_drawer_on_sale": True})
    cash = charge("sale-print-cash", payments=CASH)
    card = charge("sale-print-card")
    by_key = {job.job_key: job for job in jobs()}
    assert by_key[f"sale-{cash.id}-receipt"].open_drawer is True
    assert by_key[f"sale-{card.id}-receipt"].open_drawer is False


def test_with_the_receipt_off_only_cash_opens_the_drawer(bar, till):
    run("printing.settings.update", {"print_receipt_on_sale": False, "open_drawer_on_sale": True})
    cash = charge("sale-print-cash", payments=CASH)
    card = charge("sale-print-card")
    assert [(job.kind, job.open_drawer, job.job_key) for job in jobs()] == [("drawer", True, f"sale-{cash.id}-receipt")]
    assert (cash.printed.queued, card.printed.queued) == (True, False)


def test_without_a_printer_that_takes_the_receipt_the_screen_prints_it(bar):
    assert charge().printed.queued is False
    # The computer's printer takes an A4 page, not a receipt: the paper would wait for ever.
    run("printing.printer.create", {"name": "Office", "kind": "system", "usage": "receipt"})
    assert charge("sale-print-2").printed.queued is False
    assert not PrintJob.objects.exists()


def test_without_printing_in_the_business_the_charge_goes_on(bar, till, monkeypatch):
    monkeypatch.delitem(registry, "printing.job.create")
    out = charge()
    assert out.printed.queued is False
    assert Sale.objects.filter(pk=out.id, status="completed").exists()


def test_a_refusal_of_printing_never_spoils_the_charge(bar, till):
    seller = ctx_for()
    out = charge(ctx=dataclasses.replace(seller, permissions=seller.permissions - {"printing.print"}))
    assert out.printed.queued is False
    assert Sale.objects.filter(pk=out.id, status="completed").exists() and not PrintJob.objects.exists()


def test_a_retry_of_the_charge_prints_one_receipt(bar, till):
    first, again = charge(), charge()
    assert again.id == first.id
    assert len(jobs()) == 1


def test_a_ticket_whose_fiscal_document_is_pending_is_left_to_the_screen(product, till):
    """No issuer yet: Invoicing leaves the ticket pending, and the paper never poses as issued."""
    product("Coffee", "COF", 150, "restaurant.drink")
    out = charge()
    assert out.invoice_status == "pending"
    assert out.printed.queued is False
    assert run("sale.sale.print", {"sale_id": str(out.id)}).queued is False
    assert not PrintJob.objects.exists()


def test_a_reprint_is_a_copy_with_its_own_key_each_time(bar, till):
    out = charge()
    first = run("sale.sale.print", {"sale_id": str(out.id)})
    second = run("sale.sale.print", {"sale_id": str(out.id)})
    assert (first.queued, first.printer, second.queued) == (True, "Till", True)
    original, *copies = jobs()
    assert original.document["duplicate"] is False
    assert [job.document["duplicate"] for job in copies] == [True, True]
    assert len({job.job_key for job in jobs()}) == 3
    assert all(job.reference == out.invoice_number for job in jobs())


def test_the_first_paper_after_charging_can_be_the_original(bar, till):
    """With «print at checkout» off, the till's own «Print» right after charging is the original."""
    run("printing.settings.update", {"print_receipt_on_sale": False})
    out = charge()
    assert out.printed.queued is False
    assert run("sale.sale.print", {"sale_id": str(out.id), "duplicate": False}).queued is True
    (job,) = jobs()
    assert job.document["duplicate"] is False


def test_the_bill_of_a_check_prints_with_its_lines(bar, till):
    order = run("sale.order.open", {"lines": [{"product": "COF", "quantity": "2"}], "label": "Table 4"})
    out = run("sale.order.print_bill", {"order_id": str(order.id)})
    (job,) = jobs()
    assert (out.queued, out.job_id, out.printer) == (True, job.id, "Till")
    assert (job.document_type, job.reference, job.source_app) == ("prebill", "Table 4", "sale")
    assert job.document["customer_name"] == "Table 4" and job.document["total"] == 3.0
    # Each press is a bill of its own; the check stays open and nothing is charged.
    assert run("sale.order.print_bill", {"order_id": str(order.id)}).queued is True
    assert len(jobs()) == 2 and not Sale.objects.exists()


def test_the_employee_at_the_till_gets_the_receipt_and_the_drawer(bar, till):
    """Whoever charges, not only the owner (pm#630): an employee's cash charge queues its receipt, with its QR and the
    order to open the drawer."""
    run("printing.settings.update", {"open_drawer_on_sale": True})
    out = charge("sale-print-employee", payments=CASH, ctx=ctx_for("hub_employee"))
    (job,) = jobs()
    assert out.printed.queued is True
    assert (job.job_key, job.open_drawer) == (f"sale-{out.id}-receipt", True)
    assert job.document["qr_data"].startswith("https://")
