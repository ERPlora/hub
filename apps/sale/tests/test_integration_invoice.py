"""Sale and Invoicing together, no mocks (SALE-F01, F04, F29–F31; INVOICE-F01, F02, F07, F09, F10): real
charges, refunds and voids made with the till's own operations, priced with Taxes' real rules, and the
fiscal documents Invoicing issues from them.

What is charged and what is declared never drift apart: the ticket closes each fiscal key once, as the
invoice does, so the breakdown of both is the same to the cent.
"""

from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone
from live.errors import Conflict
from live.operations import registry

from apps.invoice.models import Invoice, InvoiceSeries
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


@pytest.fixture
def issuer(db):
    """The business's tax identity, set up as the owner would (Invoicing → Issuer)."""
    return run("invoice.issuer.update", ISSUER)


@pytest.fixture
def bar(product):
    product("Tapa", "TAP", 150, "restaurant.food")
    product("Cane", "CAN", 150, "restaurant.drink")


def charge(key, *lines, **more):
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "lines": list(lines),
            "payments": [{"method": "card"}],
            **more,
        },
    )


def document_of(sale):
    found = run("invoice.invoice.create_from_sale", {"sale_id": str(sale.id)})
    return found.invoice


def test_two_categories_at_ten_percent_declare_what_the_ticket_charged(issuer, bar):
    # 1.50 € of food and 1.50 € of drink, VAT included: one fiscal key, one rounding (2.73 + 0.27) in the
    # ticket and in its invoice.
    sale = charge("inv-key-0001", {"product": "TAP"}, {"product": "CAN"})
    invoice = document_of(sale)
    assert [(e.rate, e.base, e.quota) for e in invoice.tax_breakdown] == [
        (Decimal("10.00"), 273, 27)
    ]
    assert [(row.rate_pct, row.base, row.tax) for row in sale.breakdown] == [
        (Decimal("10.00"), 273, 27)
    ]
    assert (sale.subtotal, sale.tax_total, sale.total) == (
        invoice.base_amount,
        invoice.tax_amount,
        invoice.total_amount,
    )


# ── The fiscal chain in the same transaction (SALE-F01, F04, F30, F31; INVOICE-F01, F02, F07, F09, F10) ──

YEAR = timezone.localdate().year
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, Madrid",
}


def refund(sale, amount, reason="Broken", **more):
    payment = Sale.objects.get(pk=sale.id).payments.get()
    return run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": reason,
            "allocations": [{"payment_id": str(payment.id), "amount": amount}],
            **more,
        },
    )


def test_a_ticket_is_numbered_by_invoicing_in_the_very_charge(issuer, bar):
    sale = charge("chain-0001", {"product": "TAP"})
    assert (sale.invoice_status, sale.invoice_type, sale.invoice_number) == (
        "issued",
        "F2",
        f"TICKET-{YEAR}-000001",
    )
    ticket = Invoice.objects.get(source_sale_id=sale.id)
    assert (ticket.id, ticket.number, ticket.total_amount) == (
        sale.invoice_id,
        sale.invoice_number,
        sale.total,
    )
    # The document of the sale says the same, read again.
    again = run("sale.sale.get", {"sale_id": str(sale.id)})
    assert (again.invoice_status, again.invoice_number) == ("issued", sale.invoice_number)
    # Repeating the attempt answers the same sale and the same document: nothing is issued twice.
    replay = charge("chain-0001", {"product": "TAP"})
    assert (replay.already, replay.invoice_number) == (True, sale.invoice_number)
    assert Invoice.objects.count() == 1


def test_every_line_of_the_ticket_declares_what_its_line_of_the_sale_charged(issuer, bar):
    # Line by line, not only in total: the sale shares each key's base by weight as Invoicing does, so
    # the base and the tax of every sale line are those of its invoice line.
    from apps.invoice.models import InvoiceLine
    from apps.sale.models import SaleLine

    sale = charge("chain-0050", {"product": "TAP"}, {"product": "CAN"}, {"product": "CAN"})
    lines = SaleLine.objects.filter(sale_id=sale.id).order_by("position")
    declared = {
        line.sale_line_id: (line.base_amount, line.tax_amount, line.total_amount)
        for line in InvoiceLine.objects.filter(invoice_id=sale.invoice_id)
    }
    assert [(line.net_amount, line.tax_amount, line.line_total) for line in lines] == [
        declared[line.id] for line in lines
    ]


def test_an_invoice_to_a_company_card_is_addressed_to_the_company(issuer, bar, customer):
    # The card of Lucía, who works for «Estudio Ana SL»: the invoice names the company (VeriFactu's
    # NombreRazon goes with the company's tax ID), never the person with the company's NIF.
    card = customer(
        "Lucía Pérez",
        company_name="Estudio Ana SL",
        tax_id="B12345674",
        address="Calle Luna 3",
        postal_code="28001",
        city="Madrid",
    )
    sale = charge("chain-0020", {"product": "TAP"}, document_type="invoice", customer_id=str(card.id))
    invoice = Invoice.objects.get(pk=sale.invoice_id)
    assert (invoice.invoice_type, invoice.customer_name, invoice.customer_tax_id) == (
        "F1",
        "Estudio Ana SL",
        "B12345674",
    )
    assert Sale.objects.get(pk=sale.id).customer_name == "Estudio Ana SL"


def test_an_invoice_whose_recipient_invoicing_refuses_is_a_422_never_a_pending_document(
    issuer, bar, customer
):
    # What the cashier typed (or the card says) is the input of an F1: Invoicing refusing it is a 422 to
    # fix now, not a document left pending with a recipient that will never be valid.
    from live.errors import InvalidPayload

    from apps.customer.models import Customer

    card = customer("Ana Smith", tax_id="GB123456789", address="1 High St", city="London")
    Customer.objects.filter(pk=card.id).update(country="UK")  # an old card, before countries were checked
    with pytest.raises(InvalidPayload) as refused:
        charge(
            "chain-0021",
            {"product": "TAP"},
            document_type="invoice",
            customer_id=str(card.id),
            customer_id_type="04",
        )
    assert "customer_country" in refused.value.fields
    assert not Sale.objects.exists() and Invoice.objects.count() == 0


def test_a_refusal_of_the_input_of_a_full_invoice_stops_the_charge(issuer, bar, monkeypatch):
    from live.errors import InvalidPayload

    def refuse(ctx, data):
        raise InvalidPayload("Bad recipient", fields={"customer_name": "Bad recipient"})

    monkeypatch.setattr(registry["invoice.invoice.create_from_sale"], "fn", refuse)
    with pytest.raises(InvalidPayload):
        charge("chain-0022", {"product": "TAP"}, document_type="invoice", **RECIPIENT)
    assert not Sale.objects.exists()
    # A ticket is not the cashier's input: the same refusal leaves its document pending.
    assert charge("chain-0023", {"product": "TAP"}).invoice_status == "pending"


def test_a_sale_charged_as_an_invoice_is_a_full_invoice_in_the_same_commit(issuer, bar):
    sale = charge("chain-0002", {"product": "TAP"}, document_type="invoice", **RECIPIENT)
    assert (sale.invoice_status, sale.invoice_type, sale.invoice_number) == (
        "issued",
        "F1",
        f"FACT-{YEAR}-000001",
    )
    invoice = Invoice.objects.get(pk=sale.invoice_id)
    assert (invoice.customer_name, invoice.customer_tax_id) == (
        "Talleres Pérez SL",
        "B12345674",
    )
    # One commit: if the charge does not commit, neither the sale nor its number exist.
    with pytest.raises(RuntimeError), transaction.atomic():
        charge("chain-0003", {"product": "CAN"}, document_type="invoice", **RECIPIENT)
        raise RuntimeError("the charge never commits")
    assert Sale.objects.count() == Invoice.objects.count() == 1
    assert InvoiceSeries.objects.get(code="FACT", year=YEAR).current_number == 1


def test_each_part_of_a_check_charged_apart_is_its_own_ticket(issuer, bar):
    order = run("sale.order.open", {"lines": [{"product": "TAP"}, {"product": "CAN"}]})
    first_line = order.lines[0].id
    first = run(
        "sale.sale.complete",
        {
            "idempotency_key": "chain-0004",
            "order_id": str(order.id),
            "line_ids": [str(first_line)],
            "payments": [{"method": "card"}],
        },
    )
    rest = run(
        "sale.sale.complete",
        {"idempotency_key": "chain-0005", "order_id": str(order.id), "payments": [{"method": "card"}]},
    )
    assert [first.invoice_number, rest.invoice_number] == [
        f"TICKET-{YEAR}-000001",
        f"TICKET-{YEAR}-000002",
    ]


def test_a_refund_is_rectified_in_the_same_operation(issuer, bar):
    sale = charge("chain-0006", {"product": "TAP"}, {"product": "CAN"})
    partial = refund(sale, 100)
    assert (partial.invoice_status, partial.invoice_type, partial.invoice_number) == (
        "issued",
        "R5",
        f"RECT-{YEAR}-000001",
    )
    rectification = Invoice.objects.get(number=partial.invoice_number)
    assert (rectification.total_amount, rectification.rectifies.number) == (
        -100,
        sale.invoice_number,
    )
    rest = refund(sale, 200, idempotency_key="chain-refund-0001")
    assert rest.invoice_number == f"RECT-{YEAR}-000002" and rest.fully_refunded is True
    assert Invoice.objects.get(pk=sale.invoice_id).status == "cancelled"
    # The same refund again answers what it recorded, with its rectification: nothing new is issued.
    replay = refund(sale, 200, idempotency_key="chain-refund-0001")
    assert (replay.already, replay.invoice_status, replay.invoice_number) == (
        True,
        "issued",
        rest.invoice_number,
    )
    assert Invoice.objects.filter(invoice_type="R5").count() == 2


def test_a_refund_of_a_full_invoice_is_an_r1(issuer, bar):
    sale = charge("chain-0007", {"product": "TAP"}, document_type="invoice", **RECIPIENT)
    rectified = refund(sale, sale.total)
    assert (rectified.invoice_type, rectified.invoice_status) == ("R1", "issued")


def test_a_voided_ticket_is_rectified_whole_as_r5(issuer, bar):
    sale = charge("chain-0008", {"product": "TAP"})
    voided = run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    assert (voided.void_invoice_status, voided.void_invoice_number) == (
        "issued",
        f"RECT-{YEAR}-000001",
    )
    rectification = Invoice.objects.get(number=voided.void_invoice_number)
    assert (rectification.invoice_type, rectification.total_amount) == ("R5", -sale.total)
    assert Invoice.objects.get(pk=sale.invoice_id).status == "cancelled"
    read = run("sale.sale.get", {"sale_id": str(sale.id)})
    assert read.void_invoice_number == voided.void_invoice_number


# ── Invoicing absent, off or refusing ───────────────────────────────────────────────────────────


@pytest.fixture
def invoicing_off(monkeypatch):
    """Invoicing not installed in this business: its operations are not there (as with app_inactive)."""

    def turn_off():
        for name in [name for name in registry if name.startswith("invoice.")]:
            monkeypatch.delitem(registry, name)

    return turn_off


def test_without_invoicing_a_sale_is_a_ticket_without_fiscal_document(bar, invoicing_off):
    invoicing_off()
    sale = charge("chain-0010", {"product": "TAP"}, {"product": "CAN"})
    assert (sale.invoice_status, sale.invoice_number, sale.invoice_id) == (
        "unavailable",
        "",
        None,
    )
    assert refund(sale, 100).invoice_status == "unavailable"
    other = charge("chain-0011", {"product": "TAP"})
    voided = run("sale.sale.void", {"sale_id": str(other.id), "reason": "x"})
    assert voided.void_invoice_status == "unavailable"
    assert Invoice.objects.count() == 0


def test_a_refusal_of_invoicing_never_stops_the_charge_and_the_document_waits(bar):
    # No issuer yet (INVOICE-F06): the charge goes through, nothing of Invoicing is written and the
    # document is issued by Invoicing's own reaction once the issuer exists, which gives the sale its
    # number in that same transaction; the document's notice, handed to Sales afterwards, changes nothing.
    from live.context import system_context
    from live.models import OutboxEvent

    from apps.invoice import events as invoice_events
    from apps.sale import events as sale_events
    from apps.sale.tests.conftest import A

    sale = charge("chain-0012", {"product": "TAP"})
    assert (sale.status, sale.invoice_status, sale.invoice_number) == ("completed", "pending", "")
    assert Invoice.objects.count() == 0 and not InvoiceSeries.objects.exists()
    run("invoice.issuer.update", ISSUER)
    completed = OutboxEvent.objects.get(name="sale.sale.completed")
    issued = invoice_events.react(A, completed.name, completed.payload)
    read = run("sale.sale.get", {"sale_id": str(sale.id)})
    assert (read.invoice_status, read.invoice_number, read.invoice_id) == (
        "issued",
        issued.invoice.number,
        issued.invoice.id,
    )
    notice = (
        OutboxEvent.objects.filter(name="invoice.invoice.issued").order_by("-created_at", "-id").first()
    )
    assert sale_events.react(A, notice.name, notice.payload).recorded is False
    assert system_context(A).actor  # the reaction ran as the platform


def test_in_production_without_a_way_to_the_aeat_the_charge_is_refused(issuer, bar, settings):
    # Working-rules §15 (the old Hub's enforce_fiscal_road, HUB-1935): a business that files for real never
    # charges a sale whose ticket could never reach the AEAT. VeriFactu's refusal is not a document that
    # waits: it reaches the cashier as it is and nothing is charged, numbered or sealed.
    from live.context import system_context

    from apps.sale.tests.conftest import A

    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    system = system_context(A)
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": True, "representation": {"status": "approved"}},
        system,
    )
    run("verifactu.config.go_live")
    run("verifactu.config.sync", {"version": 2, "live_paid": False}, system)
    with pytest.raises(Conflict) as refused:
        charge("chain-0099", {"product": "TAP"})
    assert refused.value.code == "verifactu.live_option_unpaid"
    assert not Sale.objects.exists()
    assert not Invoice.objects.exists()
    assert not InvoiceSeries.objects.filter(current_number__gt=0).exists()


@pytest.mark.parametrize(
    "lost", ["own_certificate_unreadable", "gateway_unavailable", "production_closed"]
)
def test_in_production_a_server_that_cannot_reach_the_aeat_refuses_the_charge(
    issuer, bar, settings, lost
):
    # The same rule when what is missing is the server's: the key that opens the own certificate (missing or
    # rotated), ERPlora's gateway or the opening of real filing. The charge never stays «pending».
    from apps.verifactu import certificates
    from apps.verifactu.tests.conftest import b64, make_p12

    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    run(
        "verifactu.certificate.upload",
        {"p12_base64": b64(make_p12()), "password": "secret"},
    )
    run("verifactu.config.update", {"route": "own"})
    run("verifactu.config.go_live")
    if lost == "own_certificate_unreadable":
        settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    elif lost == "gateway_unavailable":
        settings.VERIFACTU_GATEWAY_URL = ""
    else:
        settings.VERIFACTU_PRODUCTION_ENABLED = False

    with pytest.raises(Conflict) as refused:
        charge("chain-0098", {"product": "TAP"})

    assert refused.value.code == f"verifactu.{lost}"
    assert not Sale.objects.exists()
    assert not Invoice.objects.exists()
    assert not InvoiceSeries.objects.filter(current_number__gt=0).exists()


def test_the_seller_without_the_right_to_invoice_still_charges(issuer, bar):
    ctx = ctx_for("hub_employee")
    ctx = type(ctx)(
        scope=ctx.scope,
        actor=ctx.actor,
        permissions=ctx.permissions - {"invoice.add_invoice"},
    )
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "chain-0013", "lines": [{"product": "TAP"}], "payments": [{"method": "card"}]},
        ctx,
    )
    assert (sale.status, sale.invoice_status) == ("completed", "pending")


# ── A document that waits has a way out in phase 1 (no relay): retry, «Issue now», the void ─────────


def test_retrying_a_charge_whose_document_waits_issues_it_now(bar):
    # No issuer at the till: the ticket waits. The same attempt sent again once the issuer exists issues
    # it (the charge itself is not repeated), and a third time changes nothing.
    sale = charge("chain-0030", {"product": "TAP"})
    assert sale.invoice_status == "pending"
    run("invoice.issuer.update", ISSUER)
    again = charge("chain-0030", {"product": "TAP"})
    assert (again.already, again.id, again.invoice_status, again.invoice_type) == (
        True,
        sale.id,
        "issued",
        "F2",
    )
    assert again.invoice_number == f"TICKET-{YEAR}-000001"
    assert charge("chain-0030", {"product": "TAP"}).invoice_number == again.invoice_number
    assert Invoice.objects.count() == 1 and Sale.objects.count() == 1


def test_issue_now_issues_every_document_that_waits_and_says_so(bar):
    from live.models import OutboxEvent

    first = charge("chain-0031", {"product": "TAP"}, {"product": "CAN"})
    refund(first, 100)
    second = charge("chain-0032", {"product": "TAP"})
    run("sale.sale.void", {"sale_id": str(second.id), "reason": "Wrong table"})
    rows = {row.id: row for row in run("sale.sale.list", {"limit": 10}).rows}
    assert rows[first.id].documents_pending and rows[second.id].documents_pending
    assert [r.invoice_status for r in run("sale.refund.list", {"sale_id": str(first.id)}).rows] == ["pending"]

    run("invoice.issuer.update", ISSUER)
    issued = run("sale.sale.issue_documents", {"sale_id": str(first.id)})
    assert (issued.invoice_status, issued.invoice_type, issued.documents_pending) == ("issued", "F2", False)
    (row,) = run("sale.refund.list", {"sale_id": str(first.id)}).rows
    assert (row.invoice_status, row.invoice_number) == ("issued", f"RECT-{YEAR}-000001")
    voided = run("sale.sale.issue_documents", {"sale": second.number})
    assert (voided.invoice_status, voided.void_invoice_status) == ("issued", "issued")
    assert voided.void_invoice_number == f"RECT-{YEAR}-000002"
    assert Invoice.objects.get(number=voided.void_invoice_number).invoice_type == "R5"
    # One notice per document issued now (the lists and the papers follow them).
    assert OutboxEvent.objects.filter(name="sale.sale.invoiced").count() == 4
    # Nothing left: asking again issues nothing and says nothing.
    assert run("sale.sale.issue_documents", {"sale_id": str(first.id)}).documents_pending is False
    assert OutboxEvent.objects.filter(name="sale.sale.invoiced").count() == 4
    assert Invoice.objects.count() == 4


def test_issue_now_says_why_it_cannot_and_changes_nothing(bar):
    sale = charge("chain-0033", {"product": "TAP"})
    with pytest.raises(Conflict) as refused:
        run("sale.sale.issue_documents", {"sale_id": str(sale.id)})
    assert refused.value.code == "invoice.issuer_missing"
    assert Sale.objects.get(pk=sale.id).invoice_status == "pending"


def test_issue_now_of_an_invoice_keeps_the_recipient_the_cashier_typed(bar):
    # A full invoice to a recipient typed at the till (no card): the sale keeps its fiscal copy, so the
    # invoice issued later names the same company with the same tax ID.
    sale = charge("chain-0034", {"product": "TAP"}, document_type="invoice", **RECIPIENT)
    assert sale.invoice_status == "pending"
    run("invoice.issuer.update", ISSUER)
    issued = run("sale.sale.issue_documents", {"sale_id": str(sale.id)})
    invoice = Invoice.objects.get(pk=issued.invoice_id)
    assert (invoice.invoice_type, invoice.customer_name, invoice.customer_tax_id, invoice.customer_address) == (
        "F1",
        "Talleres Pérez SL",
        "B12345674",
        "Calle Luna 3, Madrid",
    )


def test_voiding_a_sale_whose_ticket_waits_issues_the_ticket_first_then_its_rectification(bar):
    sale = charge("chain-0035", {"product": "TAP"})
    run("invoice.issuer.update", ISSUER)
    voided = run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    assert (voided.invoice_status, voided.invoice_number) == ("issued", f"TICKET-{YEAR}-000001")
    assert (voided.void_invoice_status, voided.void_invoice_number) == ("issued", f"RECT-{YEAR}-000001")
    assert voided.documents_pending is False


def test_without_an_issuer_a_void_still_goes_through_and_both_documents_wait_in_sight(bar):
    sale = charge("chain-0036", {"product": "TAP"})
    voided = run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    assert (voided.status, voided.invoice_status, voided.void_invoice_status) == ("voided", "pending", "pending")
    assert voided.documents_pending is True


# ── Invoicing failing inside the charge (H5) ─────────────────────────────────────────────────────


def test_a_refusal_after_numbering_gives_the_number_back_and_the_document_waits(issuer, bar):
    # The ticket series' counter set back by hand: Invoicing numbers TICKET-…-000001 again, finds it taken
    # and refuses (invoice.number_taken) AFTER raising the counter. Its savepoint gives the number back;
    # the sale is charged and its document waits.
    first = charge("chain-0040", {"product": "TAP"})
    assert first.invoice_number == f"TICKET-{YEAR}-000001"
    InvoiceSeries.objects.filter(code="TICKET").update(current_number=0)
    second = charge("chain-0041", {"product": "TAP"})
    assert (second.status, second.invoice_status, second.invoice_number) == ("completed", "pending", "")
    assert InvoiceSeries.objects.get(code="TICKET").current_number == 0
    assert Invoice.objects.count() == 1


def test_an_unexpected_error_inside_invoicing_undoes_the_whole_charge(issuer, bar, monkeypatch):
    from apps.sale.models import Order, SaleCounter

    def broken(ctx, data):
        raise RuntimeError("a bug in Invoicing")

    monkeypatch.setattr(registry["invoice.invoice.create_from_sale"], "fn", broken)
    with pytest.raises(RuntimeError):
        charge("chain-0042", {"product": "TAP"})
    # Nothing of the charge is left: no sale, no counter check, no number of the day burned.
    assert not Sale.objects.exists() and not Order.objects.exists()
    assert not SaleCounter.objects.filter(last__gt=0).exists()
