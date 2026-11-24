"""Sales asks Printing for its paper by name (PRINTING-F07, F08, F09, F13; SALE-F21, F29): the receipt at checkout
inside the charge's own
transaction, a reprint marked as a copy and the bill of a check. No mocks: Inventory owns the products,
Invoicing numbers the ticket and VeriFactu seals it, Printing queues the paper. Without Printing on, without a
printer that takes the paper or with a fiscal document still pending, nothing is queued: the charge goes on and
the screen prints it, and a reprint or a bill fails with why, so the assistant's receipt says it was not done; a
refusal of Printing never spoils the charge.
"""

import dataclasses
import datetime as dt

import pytest
from django.test import RequestFactory
from live.errors import Conflict
from live.operations import registry

from apps.printing.models import PrintJob
from apps.sale.models import Order, Sale
from apps.sale.tests.conftest import HUB_DB, confirmed_by_the_assistant, ctx_for, run
from base.business import paper_date
from base.models.profile import Profile
from apps.sale.tests.test_integration_invoice import ISSUER

pytestmark = HUB_DB

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


def not_printed(name: str, data: dict, ctx=None) -> str:
    """The code the print ``name`` fails with; nothing is queued."""
    with pytest.raises(Conflict) as failed:
        run(name, data, ctx)
    assert not PrintJob.objects.exists()
    return failed.value.code


def open_check():
    return run("sale.order.open", {"lines": [{"product": "COF", "quantity": "2"}], "label": "Table 4"})


@pytest.fixture
def account(make_user):
    """``account(username, **fields)``: a person with a session in the business, named as their account says."""

    def make(username: str, **fields):
        user = make_user(username)
        for field, value in fields.items():
            setattr(user, field, value)
        user.save()
        return ctx_for(actor=user)

    return make


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
    assert (paper["business_name"], paper["vat_number"], paper["receipt_id"], paper["duplicate"], paper["total"]) == (
        ISSUER["legal_name"],
        ISSUER["tax_id"],
        out.invoice_number,
        False,
        3.0,
    )
    # The receipt header goes under the issuer as an addition; its line that repeats the issuer's street stays.
    assert paper["business_address"].split("\n")[-2:] == ["Bar Ana", "Calle Mayor 1"]
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
    assert not_printed("sale.sale.print", {"sale_id": str(out.id)}) == "sale.document_pending"


def test_a_record_that_cannot_be_read_keeps_the_receipt_from_the_queue(bar, till):
    """Never a paper without its QR (VERIFACTU-F19): VeriFactu sealed the ticket but its record cannot be read, so
    nothing is queued (the screen's paper says why) and the charge goes on."""
    seller = ctx_for()
    blind = dataclasses.replace(seller, permissions=seller.permissions - {"verifactu.view_record"})
    out = charge(ctx=blind)
    assert out.invoice_status == "issued"
    assert out.printed.queued is False
    assert Sale.objects.filter(pk=out.id, status="completed").exists()
    assert not_printed("sale.sale.print", {"sale_id": str(out.id)}, blind) == "sale.record_unreadable"


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



def test_a_reprint_says_when_the_sale_was_charged_not_the_hour_it_prints(bar, till, monkeypatch, in_business_a):
    """A coffee charged at 15:41 and reprinted at 16:20 said «16:20», the device's hour, on the paper
    and not the sale's, the one on its invoice and its QR. The paper brings it, on the business's clock."""
    monkeypatch.setattr(in_business_a, "timezone", "Europe/Madrid")
    out = charge("sale-print-date")
    Sale.objects.filter(pk=out.id).update(created_at=dt.datetime(2026, 11, 21, 14, 41, tzinfo=dt.UTC))
    run("sale.sale.print", {"sale_id": str(out.id)})
    original, copy = jobs()
    assert original.document["date"] == paper_date(out.created_at)
    assert copy.document["date"] == "21/11/2026 15:41"

def test_the_first_paper_after_charging_can_be_the_original(bar, till):
    """With «print at checkout» off, the till's own «Print» right after charging is the original."""
    run("printing.settings.update", {"print_receipt_on_sale": False})
    out = charge()
    assert out.printed.queued is False
    assert run("sale.sale.print", {"sale_id": str(out.id), "duplicate": False}).queued is True
    (job,) = jobs()
    assert job.document["duplicate"] is False


def test_a_reprint_no_printer_takes_is_not_printed(bar):
    sale = {"sale_id": str(charge().id)}
    assert not_printed("sale.sale.print", sale) == "sale.no_printer"
    # The computer's printer takes an A4 page, not a receipt: the paper would wait for ever.
    run("printing.printer.create", {"name": "Office", "kind": "system", "usage": "receipt"})
    assert not_printed("sale.sale.print", sale) == "sale.no_printer"


def test_without_printing_in_the_business_neither_a_reprint_nor_a_bill_is_printed(bar, till, monkeypatch):
    monkeypatch.delitem(registry, "printing.job.create")
    assert not_printed("sale.sale.print", {"sale_id": str(charge().id)}) == "sale.no_printer"
    assert not_printed("sale.order.print_bill", {"order_id": str(open_check().id)}) == "sale.no_printer"


def test_a_refusal_of_printing_leaves_a_reprint_unprinted(bar, till):
    out = charge()
    PrintJob.objects.all().delete()
    seller = ctx_for()
    refused = dataclasses.replace(seller, permissions=seller.permissions - {"printing.print"})
    assert not_printed("sale.sale.print", {"sale_id": str(out.id)}, refused) == "sale.no_printer"


def test_a_bill_no_printer_takes_is_not_printed_and_the_check_is_not_noted(bar):
    """Nothing came out for the table: its plan does not say «Bill requested» (TABLE-F34)."""
    order = open_check()
    assert not_printed("sale.order.print_bill", {"order_id": str(order.id)}) == "sale.no_printer"
    assert Order.objects.get(pk=order.id).bill_printed_at is None


# ── From the assistant (BASE-F97, BASE-F99) ───────────────────────────────────────────────────────────────────────────
# hub#2328: with no printer for the paper, the receipt under the answer said «Done» and nothing was printed. A paper
# no printer takes is not done: the receipt says why, and only a paper a printer took says «Done».

NO_PRINTER_FOR_THE_SALE = {
    "es": "Ninguna impresora de tiques recibe el papel de esta venta: abre la venta para imprimirlo en este dispositivo.",
    "en": "No receipt printer takes this sale's paper: open the sale to print it on this device.",
}


@pytest.mark.parametrize("language", ["es", "en"])
def test_from_the_assistant_a_reprint_no_printer_takes_is_not_done_and_says_why(bar, language):
    sale = {"sale_id": str(charge().id)}
    row = confirmed_by_the_assistant("sale.sale.print", sale, ctx_for(language=language))
    said = NO_PRINTER_FOR_THE_SALE[language]
    assert (row["outcome"], row["code"], row["reason"]) == ("error", "sale.no_printer", {language: said})
    assert not PrintJob.objects.exists()


def test_from_the_assistant_a_reprint_of_a_pending_document_says_it_is_pending(product, till):
    product("Coffee", "COF", 150, "restaurant.drink")
    row = confirmed_by_the_assistant("sale.sale.print", {"sale_id": str(charge().id)}, ctx_for(language="es"))
    assert (row["outcome"], row["code"]) == ("error", "sale.document_pending")
    assert row["reason"] == {"es": "Su documento fiscal sigue pendiente: abre la venta para emitirlo."}


def test_from_the_assistant_a_reprint_whose_record_cannot_be_read_says_it_never_prints_without_its_qr(bar, till):
    out = charge()
    PrintJob.objects.all().delete()
    seller = ctx_for(language="es")
    blind = dataclasses.replace(seller, permissions=seller.permissions - {"verifactu.view_record"})
    row = confirmed_by_the_assistant("sale.sale.print", {"sale_id": str(out.id)}, blind)
    assert (row["outcome"], row["code"]) == ("error", "sale.record_unreadable")
    assert row["reason"] == {"es": "No se pudo leer su registro de VeriFactu, y su papel nunca se imprime sin su QR."}
    assert not PrintJob.objects.exists()


def test_from_the_assistant_a_bill_no_printer_takes_is_not_done_and_says_why(bar):
    row = confirmed_by_the_assistant("sale.order.print_bill", {"order_id": str(open_check().id)}, ctx_for(language="es"))
    assert (row["outcome"], row["code"]) == ("error", "sale.no_printer")
    assert row["reason"] == {
        "es": "Ninguna impresora de tiques recibe esta cuenta: ábrela en Ventas para imprimirla en este dispositivo."
    }


def test_from_the_assistant_a_reprint_and_a_bill_a_printer_took_are_done(bar, till):
    out, order = charge(), open_check()
    seller = ctx_for(language="es")
    assert [
        (row["outcome"], row["code"], row["reason"])
        for row in (
            confirmed_by_the_assistant("sale.sale.print", {"sale_id": str(out.id)}, seller),
            confirmed_by_the_assistant("sale.order.print_bill", {"order_id": str(order.id)}, seller),
        )
    ] == [("ok", "", {}), ("ok", "", {})]
    assert [job.document_type for job in jobs()][1:] == ["receipt", "prebill"]


def test_the_bill_of_a_check_prints_with_its_lines(bar, till):
    order = open_check()
    out = run("sale.order.print_bill", {"order_id": str(order.id)})
    (job,) = jobs()
    assert (out.queued, out.job_id, out.printer) == (True, job.id, "Till")
    assert (job.document_type, job.reference, job.source_app) == ("prebill", "Table 4", "sale")
    assert job.document["customer_name"] == "Table 4" and job.document["total"] == 3.0
    # The app's bill prints no ``vat_number``: the business's tax ID closes the address (hub#458).
    assert job.document["business_name"] == ISSUER["legal_name"]
    assert job.document["business_address"].split("\n")[-1] == f"Tax ID: {ISSUER['tax_id']}"
    # Each press is a bill of its own; the check stays open and nothing is charged.
    assert run("sale.order.print_bill", {"order_id": str(order.id)}).queued is True
    assert len(jobs()) == 2 and not Sale.objects.exists()


def at_the_till(device: str, role: str = "hub_manager"):
    """Someone at the till ``device``: the SPA names its device in ``X-Device-Id`` on every request."""
    return dataclasses.replace(ctx_for(role), request=RequestFactory().post("/api/sale/sales", HTTP_X_DEVICE_ID=device))


def test_with_two_tills_the_receipt_the_drawer_and_the_bill_come_out_at_the_till_that_asks(bar, till):
    """PRINTING-F22: charging on the terrace prints on the terrace's receipt printer and opens its drawer; the bar's
    printer prints nothing."""
    terrace = run(
        "printing.printer.create",
        {"name": "Till 2", "kind": "network", "address": "192.168.1.51", "usage": "receipt"},
    )
    for device, printer in (("bar-till", till), ("terrace-till", terrace)):
        run("printing.device.register", {"name": device, "printers": [str(printer.id)]}, at_the_till(device))
    run("printing.settings.update", {"open_drawer_on_sale": True})
    out = charge("sale-print-terrace", payments=CASH, ctx=at_the_till("terrace-till", "hub_employee"))
    (job,) = jobs()
    assert out.printed.printer == "Till 2"
    assert (job.printer.name, job.open_drawer) == ("Till 2", True)
    order = run("sale.order.open", {"lines": [{"product": "COF", "quantity": "1"}], "label": "Table 4"})
    bill = run("sale.order.print_bill", {"order_id": str(order.id)}, at_the_till("terrace-till", "hub_employee"))
    assert bill.printer == "Till 2"
    assert {job.printer.name for job in jobs()} == {"Till 2"}


def test_the_employee_at_the_till_gets_the_receipt_and_the_drawer(bar, till):
    """Whoever charges, not only the owner: an employee's cash charge queues its receipt, with its QR and the
    order to open the drawer."""
    run("printing.settings.update", {"open_drawer_on_sale": True})
    out = charge("sale-print-employee", payments=CASH, ctx=ctx_for("hub_employee"))
    (job,) = jobs()
    assert out.printed.queued is True
    assert (job.job_key, job.open_drawer) == (f"sale-{out.id}-receipt", True)
    assert job.document["qr_data"].startswith("https://")


def test_a_role_that_sells_without_reading_invoicing_still_prints_who_the_business_is(bar, till):
    """hub#458: the paper reads the issuer as the platform; a custom role or an API key may not read Invoicing."""
    seller = ctx_for()
    charge("sale-print-no-reading", ctx=dataclasses.replace(seller, permissions=seller.permissions - {"invoice.view_invoice"}))
    (job,) = jobs()
    assert (job.document["business_name"], job.document["vat_number"]) == (ISSUER["legal_name"], ISSUER["tax_id"])


def test_the_ticket_of_a_business_in_the_roi_prints_its_eu_vat_number_and_its_reprint_too(bar, till):
    """INVOICE-F21: with the issuer registered for intra-EU operations the printed ticket says «ESB12345674»; its QR
    keeps the bare tax ID, and a copy printed after the mark is taken off says what the original said."""
    run("invoice.issuer.update", {**ISSUER, "intra_eu_operator": True})
    out = charge("sale-print-roi")
    run("invoice.issuer.update", {**ISSUER, "intra_eu_operator": False})
    run("sale.sale.print", {"sale_id": str(out.id), "duplicate": True})
    original, copy = jobs()
    assert [original.document["vat_number"], copy.document["vat_number"]] == ["ESB12345674", "ESB12345674"]
    assert "nif=B12345674&" in original.document["qr_data"]


def test_a_reprint_says_what_its_document_says_whatever_the_issuer_becomes(bar, till):
    """hub#458: a copy names the issuer of the original, as on screen."""
    out = charge("sale-print-reprint")
    run("invoice.issuer.update", {**ISSUER, "legal_name": "Otro Nombre SL"})
    run("sale.sale.print", {"sale_id": str(out.id), "duplicate": True})
    assert [job.document["business_name"] for job in jobs()] == [ISSUER["legal_name"], ISSUER["legal_name"]]


def test_a_full_invoice_prints_both_parties(bar, till):
    """hub#458: the issuer's name and tax ID, and the recipient's name, tax ID and address (RD 1619/2012, art. 6)."""
    charge(
        "sale-print-invoice",
        document_type="invoice",
        customer_name="Javier Gomez Ruiz",
        customer_tax_id="76543210S",
        customer_address="Calle Real 2",
    )
    (job,) = jobs()
    paper = job.document
    assert job.document_type == "invoice"
    assert (paper["business_name"], paper["vat_number"]) == (ISSUER["legal_name"], ISSUER["tax_id"])
    assert (paper["customer_name"], paper["customer_tax_id"], paper["customer_address"]) == (
        "Javier Gomez Ruiz",
        "76543210S",
        "Calle Real 2",
    )


def test_the_receipt_names_who_charged_never_their_internal_id(bar, till, account):
    """hub#1985: the cashier line printed the account's internal id. It says who charged by the name the kitchen
    gives a waiter, and a copy printed later by someone else still names who charged."""
    bea = account("saas:01a13f83-5fd4-73c2-8d2c-44be64bc28a8", first_name="Bea", last_name="Ruiz")
    out = charge("sale-print-cashier", ctx=bea)
    run("sale.sale.print", {"sale_id": str(out.id)}, account("saas:02b24f94-0000-7000-8000-000000000002", first_name="Luis"))
    assert [job.document["cashier"] for job in jobs()] == ["Bea Ruiz", "Bea Ruiz"]


def test_a_full_invoice_names_who_charged_too(bar, till, account):
    charge(
        "sale-print-invoice-cashier",
        ctx=account("saas:01a13f83-5fd4-73c2-8d2c-44be64bc28a8", first_name="Bea"),
        document_type="invoice",
        customer_name="Javier Gomez Ruiz",
        customer_tax_id="76543210S",
        customer_address="Calle Real 2",
    )
    (job,) = jobs()
    assert (job.document_type, job.document["cashier"]) == ("invoice", "Bea")


def test_the_name_of_my_profile_in_this_business_is_the_one_on_the_receipt(bar, till, account):
    bea = account("saas:05e57fc7-0000-7000-8000-000000000005", first_name="Beatriz Ruiz Soler")
    Profile.objects.create(username=bea.actor.get_username(), first_name="Bea")
    charge("sale-print-profile", ctx=bea)
    (job,) = jobs()
    assert job.document["cashier"] == "Bea"


def test_without_a_name_to_print_the_receipt_has_no_cashier_line(bar, till, account):
    """The paper goes to the customer: with no name it has no cashier line, rather than an employee's e-mail (the
    SaaS names an account without a name by its address) or an internal id (an account with nothing, an API key)."""
    charge("sale-print-named-by-email", ctx=account("saas:03c35fa5-0000-7000-8000-000000000003", first_name="bea@example.com"))
    charge("sale-print-email-only", ctx=account("saas:06f68fd8-0000-7000-8000-000000000006", email="bea@example.com"))
    charge("sale-print-nameless", ctx=account("saas:04d46fb6-0000-7000-8000-000000000004"))
    charge("sale-print-platform")
    assert [("cashier" in job.document) for job in jobs()] == [False, False, False, False]
