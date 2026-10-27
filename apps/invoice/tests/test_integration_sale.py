"""Invoicing and Sales together, no mocks (INVOICE-F01, F02, F05–F07, F09, F10, F20): real charges, refunds
and voids made with the till's own operations, priced with Taxes' real rules, and their real events handed
to Invoicing's reactions as the outbox relay will.

Cases from the current product's tests: ``from_sale.hub``, ``rectify_from_refund``, ``rectify_sale_born``,
``rectify_lines`` and ``line_surcharge_rate``.
"""

import re
from decimal import Decimal

import pytest
from django.utils import timezone
from live.errors import Conflict
from live.models import OutboxEvent

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import A, ISSUER, ctx_for, deliver, run
from apps.sale import events as sale_events
from apps.sale.models import Sale, SaleLine
from apps.tax.models import TaxRule
from apps.verifactu.models import Record

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, Madrid",
}


@pytest.fixture
def shelf(product):
    product("Shampoo", "SHA", 1210, "product.generic")
    product("Wax", "WAX", 605, "product.generic")
    product("Menu", "MNU", 1100, "restaurant.food")
    product("Physio", "PHY", 4000, "service.health")


def refund(sale, amount, reason="Broken", lines=()):
    payment = Sale.objects.get(pk=sale.id).payments.get()
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": reason,
            "allocations": [{"payment_id": str(payment.id), "amount": amount}],
            "lines": list(lines),
        },
    )
    return deliver("sale.sale.refunded")


def keys(invoice):
    return {
        (e.qualification, e.rate): (e.base, e.quota, e.surcharge_quota)
        for e in invoice.tax_breakdown
    }


def newest(name):
    return OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()


# The document of a charge (INVOICE-F01, F02)


def test_a_ticket_becomes_one_simplified_invoice_with_the_sales_money_to_the_cent(
    issuer, shelf, charge
):
    sale = charge(
        "inv-0001",
        [{"product": "SHA", "quantity": "2"}, {"product": "MNU"}, {"product": "PHY"}],
    )
    # The till issues it while charging (sale.sale.complete → invoice.invoice.create_from_sale, in the
    # charge's own transaction); the outbox's reaction is the backup and answers that same document.
    result = deliver("sale.sale.completed")
    ticket = result.invoice
    assert Invoice.objects.filter(source_sale_id=sale.id).count() == 1
    if hasattr(sale, "invoice_number"):  # Sales returns the number it printed (tarea B of Sales)
        assert (sale.invoice_number, result.issued, result.already) == (
            ticket.number,
            False,
            True,
        )
    assert (ticket.invoice_type, ticket.number, ticket.series_code) == (
        "F2",
        f"TICKET-{TODAY.year}-000001",
        "TICKET",
    )
    assert (ticket.status, ticket.source_type, ticket.sale_id, ticket.sale_number) == (
        "paid",
        "sale",
        sale.id,
        sale.number,
    )
    assert (
        ticket.paid_at is not None
        and ticket.operation_date == Sale.objects.get(pk=sale.id).business_day
    )
    assert ticket.total_amount == sale.total == 2420 + 1100 + 4000
    assert keys(ticket) == {
        ("subject", Decimal("21.00")): (2000, 420, 0),
        ("subject", Decimal("10.00")): (1000, 100, 0),
        ("exempt", Decimal("0.00")): (4000, 0, 0),
    }
    assert [
        (line.description, line.quantity, line.total_amount) for line in ticket.lines
    ] == [
        ("Shampoo", Decimal("2.000"), 2420),
        ("Menu", Decimal("1.000"), 1100),
        ("Physio", Decimal("1.000"), 4000),
    ]
    assert (ticket.issuer_name, ticket.issuer_tax_id) == (
        "Peluquería Ana SL",
        "B12345674",
    )
    exempt = next(e for e in ticket.tax_breakdown if e.qualification == "exempt")
    assert exempt.exempt_reason == "E1"


def test_the_same_charge_delivered_twice_is_one_document_and_one_number(
    issuer, shelf, charge
):
    charge("inv-0001")
    first = deliver("sale.sale.completed")
    again = deliver("sale.sale.completed")
    assert (again.issued, again.already, again.invoice.id) == (
        False,
        True,
        first.invoice.id,
    )
    assert Invoice.objects.count() == 1
    assert InvoiceSeries.objects.get(code="TICKET", year=TODAY.year).current_number == 1


def test_a_sale_charged_as_an_invoice_is_a_full_invoice_with_the_customers_data(
    issuer, shelf, charge
):
    charge("inv-0002", [{"product": "SHA"}], document_type="invoice", **RECIPIENT)
    invoice = deliver("sale.sale.completed").invoice
    assert (invoice.invoice_type, invoice.series_code, invoice.number) == (
        "F1",
        "FACT",
        f"FACT-{TODAY.year}-000001",
    )
    assert (
        invoice.customer_name,
        invoice.customer_tax_id,
        invoice.customer_address,
    ) == (
        "Talleres Pérez SL",
        "B12345674",
        "Calle Luna 3, Madrid",
    )


def test_a_comp_and_a_discount_never_move_the_money_charged(issuer, shelf, charge):
    sale = charge(
        "inv-0003",
        [{"product": "SHA"}, {"product": "WAX", "is_gift": True}],
        discount_percent="10",
    )
    invoice = deliver("sale.sale.completed").invoice
    assert invoice.total_amount == sale.total
    assert [line.total_amount for line in invoice.lines] == [
        line.line_total for line in sale.lines
    ]


def test_four_cheap_lines_vat_included_close_once_for_the_rate(issuer, product, charge):
    product("Gum", "GUM", 50, "product.generic")
    sale = charge("inv-0004", [{"product": "GUM", "quantity": "4"}])
    invoice = deliver("sale.sale.completed").invoice
    assert invoice.total_amount == sale.total == 200
    assert keys(invoice) == {("subject", Decimal("21.00")): (165, 35, 0)}
    assert sum(line.base_amount for line in invoice.lines) == invoice.base_amount


def test_the_equivalence_surcharge_is_declared_apart_from_the_vat(
    issuer, shelf, charge
):
    root = TaxRule.objects.get(
        category__key="product.generic", country_code="ES", parent__isnull=True
    )
    run(
        "tax.rule.create",
        {
            "country_code": "ES",
            "tax_category_key": "product.generic",
            "rate_pct": "5.2",
            "tax_type": "surcharge",
            "parent_id": str(root.id),
            "component_label": "Recargo de equivalencia",
        },
    )
    sale = charge("inv-0005", [{"product": "SHA"}])
    invoice = deliver("sale.sale.completed").invoice
    entry = invoice.tax_breakdown[0]
    assert (entry.rate, entry.surcharge_rate) == (Decimal("21.00"), Decimal("5.20"))
    assert entry.base + entry.quota + entry.surcharge_quota == sale.total == 1210
    assert (invoice.lines[0].tax_rate, invoice.lines[0].surcharge_rate) == (
        Decimal("21.00"),
        Decimal("5.20"),
    )


def test_without_an_issuer_the_charge_waits_and_is_invoiced_once_it_is_set_up(
    shelf, charge
):
    charge("inv-0006")
    with pytest.raises(Conflict) as refused:
        deliver("sale.sale.completed")
    assert refused.value.code == "invoice.issuer_missing"
    assert Invoice.objects.count() == 0
    run(
        "invoice.issuer.update",
        {"legal_name": "Ana SL", "tax_id": "B12345674", "address": "Calle Mayor 1"},
    )
    assert deliver("sale.sale.completed").issued is True


def test_a_sale_is_invoiced_on_request_by_its_number(shelf, charge):
    # Charged without an issuer, the sale waits for its document (INVOICE-F06); once the issuer is set up,
    # anyone who issues invoices asks for it by the sale's number.
    sale = charge("inv-0007")
    assert not Invoice.objects.filter(source_sale_id=sale.id).exists()
    run("invoice.issuer.update", ISSUER)
    result = run(
        "invoice.invoice.create_from_sale",
        {"sale": sale.number},
        ctx_for("hub_employee"),
    )
    assert (result.issued, result.invoice.sale_number) == (True, sale.number)
    found = run("invoice.invoice.by_source", {"sale": sale.number})
    assert (found.found, found.invoice.number) == (True, result.invoice.number)


# Refunds (INVOICE-F09, F10)


def test_refunding_the_whole_ticket_rectifies_it_whole_as_r5_and_cancels_it(
    issuer, shelf, charge
):
    sale = charge("inv-0010", [{"product": "SHA", "quantity": "2"}, {"product": "MNU"}])
    ticket = deliver("sale.sale.completed").invoice
    result = refund(sale, sale.total, reason="Customer unhappy")
    rect = result.invoice
    assert (
        rect.invoice_type,
        rect.series_code,
        rect.source_type,
        rect.rectifies.number,
    ) == ("R5", "RECT", "refund", ticket.number)
    assert rect.total_amount == -ticket.total_amount
    assert [
        (line.description, line.quantity, line.total_amount) for line in rect.lines
    ] == [
        ("Shampoo", Decimal("-2.000"), -2420),
        ("Menu", Decimal("-1.000"), -1100),
    ]
    assert (rect.description, rect.refund_id is not None) == ("Customer unhappy", True)
    assert run("invoice.invoice.get", {"number": ticket.number}).status == "cancelled"


def test_the_same_refund_delivered_twice_is_one_rectification(issuer, shelf, charge):
    sale = charge("inv-0011")
    deliver("sale.sale.completed")
    first = refund(sale, 500)
    again = deliver("sale.sale.refunded")
    assert (again.issued, again.already, again.invoice.id) == (
        False,
        True,
        first.invoice.id,
    )
    assert Invoice.objects.filter(invoice_type__startswith="R").count() == 1


def test_a_partial_refund_rectifies_by_differences_and_two_add_up_to_the_cent(
    issuer, shelf, charge
):
    sale = charge("inv-0012", [{"product": "SHA"}, {"product": "MNU"}])
    ticket = deliver("sale.sale.completed").invoice
    first = refund(sale, 1000, reason="Late").invoice
    assert first.total_amount == -1000
    # Money only: prorated over every key, one line per key with its own rate (no invented rate).
    by_rate = {line.tax_rate: line for line in first.lines}
    assert set(by_rate) == {Decimal("21.00"), Decimal("10.00")}
    for entry in first.tax_breakdown:
        line = by_rate[entry.rate]
        assert (line.description, line.quantity, line.discount_amount) == (
            "Late",
            Decimal("-1.000"),
            0,
        )
        assert (line.base_amount, line.unit_price) == (entry.base, Decimal(-entry.base))
        assert line.tax_amount == entry.quota + entry.surcharge_quota
    after_first = run("invoice.invoice.get", {"number": ticket.number})
    assert (after_first.status, after_first.remaining) == (
        "paid",
        ticket.total_amount - 1000,
    )
    second = refund(sale, ticket.total_amount - 1000).invoice
    assert second.total_amount == -(ticket.total_amount - 1000)
    closed = run("invoice.invoice.get", {"number": ticket.number})
    assert (closed.status, closed.remaining) == ("cancelled", 0)
    for key, (base, quota, _surcharge) in keys(ticket).items():
        assert (
            base
            + keys(first).get(key, (0, 0, 0))[0]
            + keys(second).get(key, (0, 0, 0))[0]
            == 0
        )
        assert (
            quota
            + keys(first).get(key, (0, 0, 0))[1]
            + keys(second).get(key, (0, 0, 0))[1]
            == 0
        )


def test_after_a_partial_refund_the_preview_rectifies_what_is_left_of_the_ticket_as_r5(
    issuer, shelf, charge
):
    # INVOICE-F08 asked to the assistant: its preview, on a ticket a partial refund already rectified by differences.
    sale = charge("inv-0031", [{"product": "SHA"}, {"product": "MNU"}])
    ticket = deliver("sale.sale.completed").invoice
    refund(sale, 1000, reason="Late")
    left = ticket.total_amount - 1000
    seen = run(
        "invoice.invoice.rectification_preview",
        {"number": ticket.number, "reason": "Wrong price", "rectification_type": "R1"},
    )
    assert (seen.invoice_type, seen.whole, seen.next_number) == (
        "R5",
        False,
        f"RECT-{TODAY.year}-000002",
    )
    assert (seen.original.total_amount, seen.original.remaining, seen.total_amount) == (
        ticket.total_amount,
        left,
        -left,
    )
    # What is left, one line per key at its own rate, named by the reason.
    assert {line.tax_rate for line in seen.lines} == {Decimal("21.00"), Decimal("10.00")}
    assert {(line.description, line.quantity) for line in seen.lines} == {("Wrong price", Decimal("-1"))}
    assert sum(line.total_amount for line in seen.lines) == -left
    rect = run(
        "invoice.invoice.rectify", {"number": ticket.number, "reason": "Wrong price"}
    ).invoice
    assert (rect.number, rect.invoice_type, rect.base_amount, rect.tax_amount, rect.total_amount) == (
        seen.next_number,
        "R5",
        seen.base_amount,
        seen.tax_amount,
        seen.total_amount,
    )
    assert sorted((line.tax_rate, line.base_amount, line.total_amount) for line in rect.lines) == sorted(
        (line.tax_rate, line.base_amount, line.total_amount) for line in seen.lines
    )


def test_a_refund_of_returned_articles_rectifies_only_their_keys(issuer, shelf, charge):
    # 12.10 at 21 % and 11.00 at 10 %: the shampoo comes back, so only the 21 % is rectified.
    sale = charge("inv-0021", [{"product": "SHA"}, {"product": "MNU"}])
    deliver("sale.sale.completed")
    shampoo = Sale.objects.get(pk=sale.id).lines.get(name="Shampoo")
    rect = refund(
        sale, 1210, lines=[{"line_id": str(shampoo.id), "quantity": "1"}]
    ).invoice
    assert rect.invoice_type == "R5"
    assert keys(rect) == {("subject", Decimal("21.00")): (-1000, -210, 0)}
    assert [
        (line.description, line.quantity, line.tax_rate, line.base_amount, line.total_amount)
        for line in rect.lines
    ] == [("1 × Shampoo", Decimal("-1.000"), Decimal("21.00"), -1000, -1210)]


def test_a_refund_with_returned_articles_says_what_came_back(issuer, shelf, charge):
    sale = charge("inv-0013", [{"product": "SHA", "quantity": "3"}, {"product": "WAX"}])
    deliver("sale.sale.completed")
    shampoo = Sale.objects.get(pk=sale.id).lines.get(name="Shampoo")
    rect = refund(
        sale, 2420, lines=[{"line_id": str(shampoo.id), "quantity": "2"}]
    ).invoice
    assert rect.lines[0].description == "2 × Shampoo"


def test_a_refund_of_a_full_invoice_is_an_r1(issuer, shelf, charge):
    sale = charge(
        "inv-0014", [{"product": "SHA"}], document_type="invoice", **RECIPIENT
    )
    deliver("sale.sale.completed")
    rect = refund(sale, sale.total).invoice
    assert (rect.invoice_type, rect.customer_tax_id) == ("R1", "B12345674")


def test_a_refund_after_the_ticket_was_replaced_rectifies_the_full_invoice(
    issuer, shelf, charge
):
    sale = charge("inv-0015")
    ticket = deliver("sale.sale.completed").invoice
    full = run(
        "invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT}
    ).invoice
    assert (
        run("invoice.invoice.by_source", {"sale_id": str(sale.id)}).invoice.number
        == full.number
    )
    rect = refund(sale, sale.total).invoice
    assert (rect.invoice_type, rect.rectifies.number) == ("R1", full.number)
    assert run("invoice.invoice.get", {"number": ticket.number}).status == "paid"


def test_a_refund_that_comes_before_the_invoice_waits_for_it(shelf, charge):
    # Without an issuer the charge has no document yet: its refund waits for it, then rectifies it.
    sale = charge("inv-0016")
    payment = Sale.objects.get(pk=sale.id).payments.get()
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "x",
            "allocations": [{"payment_id": str(payment.id), "amount": sale.total}],
        },
    )
    with pytest.raises(Conflict) as refused:
        deliver("sale.sale.refunded")
    assert refused.value.code == "invoice.sale_not_invoiced"
    run("invoice.issuer.update", ISSUER)
    deliver("sale.sale.completed")
    assert deliver("sale.sale.refunded").invoice.total_amount == -sale.total


# Voids (INVOICE-F07)


def test_voiding_a_charged_ticket_rectifies_it_whole(issuer, shelf, charge):
    sale = charge("inv-0020", [{"product": "SHA"}])
    ticket = deliver("sale.sale.completed").invoice
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    result = deliver("sale.sale.voided")
    rect = result.invoice
    assert (
        rect.invoice_type,
        rect.source_type,
        rect.description,
        rect.total_amount,
    ) == ("R5", "void", "Wrong table", -ticket.total_amount)
    assert run("invoice.invoice.get", {"number": ticket.number}).status == "cancelled"
    again = deliver("sale.sale.voided")
    assert (again.issued, again.already) == (False, True)


def test_a_void_that_comes_before_the_invoice_waits_for_it(shelf, charge):
    # Without an issuer the charge has no document yet: its void waits for it, then rectifies it.
    sale = charge("inv-0021")
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "x"})
    with pytest.raises(Conflict) as refused:
        deliver("sale.sale.voided")
    assert refused.value.code == "invoice.sale_not_invoiced"
    run("invoice.issuer.update", ISSUER)
    # The ticket was given to the customer: it is invoiced even though the sale is voided now.
    assert deliver("sale.sale.completed").invoice.invoice_type == "F2"
    assert deliver("sale.sale.voided").invoice.invoice_type == "R5"


def test_a_sale_that_is_not_voided_has_no_void_to_rectify(issuer, shelf, charge):
    sale = charge("inv-0022")
    deliver("sale.sale.completed")
    with pytest.raises(Conflict) as refused:
        run("invoice.invoice.rectify_from_void", {"sale_id": str(sale.id)})
    assert refused.value.code == "invoice.sale_not_voided"


# A document that waits (INVOICE-F06, F07, F09): the relay retries it on its own (test_relay.py); Sales'
# «Issue now», or first thing its sale's next void or refund, issues it at once.


def test_an_invoice_asked_of_invoicing_by_number_is_the_sales_document_at_once_and_issue_now_issues_no_other(
    shelf, charge
):
    # INVOICE-F06: asked of Invoicing (the API, the assistant) by the sale's number, the document and the
    # sale agree when the operation ends — Invoicing tells Sales in the same transaction, never «in a few
    # seconds» through the relay.
    sale = charge("inv-0023")
    assert Sale.objects.get(pk=sale.id).invoice_status == "pending"
    run("invoice.issuer.update", ISSUER)
    asked = run(
        "invoice.invoice.create_from_sale",
        {"sale": sale.number},
        ctx_for("hub_employee"),
    )
    assert asked.issued is True
    linked = Sale.objects.get(pk=sale.id)
    assert (
        linked.invoice_status,
        linked.invoice_number,
        linked.invoice_id,
        linked.invoice_type,
    ) == ("issued", asked.invoice.number, asked.invoice.id, "F2")
    said = OutboxEvent.objects.filter(name="sale.sale.invoiced")
    assert [event.payload["number"] for event in said] == [asked.invoice.number]
    # The relay's notice comes later and changes nothing: no second write, no second «invoiced».
    again = sale_events.react(A, "invoice.invoice.issued", newest("invoice.invoice.issued").payload)
    assert (again.sale_id, again.recorded) == (sale.id, False)
    assert said.count() == 1
    # Nothing waits any more: «Issue now» issues no other document.
    issued = run("sale.sale.issue_documents", {"sale": sale.number})
    assert (issued.invoice_status, issued.invoice_number, issued.documents_pending) == (
        "issued",
        asked.invoice.number,
        False,
    )
    assert Invoice.objects.filter(source_sale_id=sale.id).count() == 1
    assert said.count() == 1


def test_issue_now_says_once_that_the_sale_has_its_document(shelf, charge):
    # «Issue now» of Sales asks Invoicing, which links the waiting sale: the sale is told once, not twice.
    sale = charge("inv-0025")
    run("invoice.issuer.update", ISSUER)
    issued = run("sale.sale.issue_documents", {"sale": sale.number})
    ticket = Invoice.objects.get(source_sale_id=sale.id)
    assert (issued.invoice_status, issued.invoice_number) == ("issued", ticket.number)
    said = OutboxEvent.objects.filter(name="sale.sale.invoiced")
    assert [event.payload["invoice_id"] for event in said] == [str(ticket.id)]


def test_a_charge_with_its_document_issued_in_it_is_not_told_later_it_has_one(issuer, shelf, charge):
    # The charge writes its own document's number (INVOICE-F01): Invoicing tells Sales only of a sale that
    # waits, so a charge records no «invoiced».
    sale = charge("inv-0026")
    assert Sale.objects.get(pk=sale.id).invoice_status == "issued"
    assert not OutboxEvent.objects.filter(name="sale.sale.invoiced").exists()


def test_the_rectifications_asked_of_invoicing_are_the_void_and_the_refund_documents_at_once(
    shelf, charge
):
    # INVOICE-F06 with F07 and F09: without an issuer, a void and a refund leave their rectifications
    # waiting; asked of Invoicing directly, each is the document of its void or its refund at once.
    voided = charge("inv-0027")
    run("sale.sale.void", {"sale_id": str(voided.id), "reason": "Wrong table"})
    refunded = charge("inv-0028")
    payment = Sale.objects.get(pk=refunded.id).payments.get()
    run(
        "sale.sale.refund",
        {
            "sale_id": str(refunded.id),
            "reason": "Broken",
            "allocations": [{"payment_id": str(payment.id), "amount": 500}],
        },
    )
    (record,) = Sale.objects.get(pk=refunded.id).refunds.all()
    assert (Sale.objects.get(pk=voided.id).void_invoice_status, record.invoice_status) == (
        "pending",
        "pending",
    )
    run("invoice.issuer.update", ISSUER)
    for sale in (voided, refunded):
        run("invoice.invoice.create_from_sale", {"sale": sale.number})

    by_void = run("invoice.invoice.rectify_from_void", {"sale_id": str(voided.id)})
    by_refund = run("invoice.invoice.rectify_from_refund", {"refund_id": str(record.id)})

    read = Sale.objects.get(pk=voided.id)
    assert (read.void_invoice_status, read.void_invoice_number) == ("issued", by_void.invoice.number)
    record.refresh_from_db()
    assert (record.invoice_status, record.invoice_number, record.invoice_type) == (
        "issued",
        by_refund.invoice.number,
        "R5",
    )
    # One «invoiced» per document; «Issue now» finds nothing left and says nothing more.
    said = OutboxEvent.objects.filter(name="sale.sale.invoiced")
    assert said.count() == 4
    for sale in (voided, refunded):
        assert run("sale.sale.issue_documents", {"sale": sale.number}).documents_pending is False
    assert said.count() == 4
    assert Invoice.objects.count() == 4


def test_issue_now_links_a_sale_whose_invoice_was_issued_before_it_was_told(shelf, charge):
    # A sale left waiting by the previous release although Invoicing had issued its ticket (asked by its
    # number, before Invoicing told Sales itself): «Issue now» gives it that ticket, issuing no other.
    sale = charge("inv-0029")
    run("invoice.issuer.update", ISSUER)
    ticket = run("invoice.invoice.create_from_sale", {"sale": sale.number}).invoice
    # The data that release left behind: the ticket exists, the sale still waits for it.
    Sale.objects.filter(pk=sale.id).update(invoice_status="pending", invoice_number="", invoice_id=None, invoice_type="")
    OutboxEvent.objects.filter(name="sale.sale.invoiced").delete()

    issued = run("sale.sale.issue_documents", {"sale": sale.number})

    assert (issued.invoice_status, issued.invoice_number, issued.invoice_id) == ("issued", ticket.number, ticket.id)
    assert Invoice.objects.filter(source_sale_id=sale.id).count() == 1
    assert OutboxEvent.objects.filter(name="sale.sale.invoiced").count() == 1


def test_a_refund_of_a_sale_whose_ticket_waits_issues_the_ticket_first_then_its_rectification(
    shelf, charge
):
    sale = charge("inv-0024")
    run("invoice.issuer.update", ISSUER)
    payment = Sale.objects.get(pk=sale.id).payments.get()
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "Broken",
            "allocations": [{"payment_id": str(payment.id), "amount": sale.total}],
        },
    )
    sale = Sale.objects.get(pk=sale.id)
    ticket = Invoice.objects.get(source_sale_id=sale.id, source_type="sale")
    assert (sale.invoice_status, sale.invoice_number, ticket.invoice_type) == (
        "issued",
        ticket.number,
        "F2",
    )
    (record,) = sale.refunds.all()
    rectification = Invoice.objects.get(number=record.invoice_number)
    assert (record.invoice_status, rectification.invoice_type, rectification.rectifies_id) == (
        "issued",
        "R5",
        ticket.id,
    )


# What a full invoice says of each line (RD 1619/2012 art. 6.1.f) and of the operation


def test_a_full_invoice_prints_each_price_without_vat_and_the_discount_apart(
    issuer, shelf, charge
):
    sale = charge(
        "inv-0022",
        [{"product": "SHA", "quantity": "2"}],
        discount_percent="10",
        document_type="invoice",
        **RECIPIENT,
    )
    invoice = deliver("sale.sale.completed").invoice
    line = invoice.lines[0]
    # 2 × 12.10 with VAT = 2 × 10.00 without it; 10 % off = 2.00 without VAT; 18.00 + 3.78 = 21.78.
    assert (
        line.quantity,
        line.unit_price,
        line.discount_amount,
        line.base_amount,
        line.tax_amount,
        line.total_amount,
    ) == (Decimal("2.000"), Decimal("1000.00"), 200, 1800, 378, 2178)
    assert invoice.total_amount == sale.total == 2178
    html = run("invoice.invoice.document", {"number": invoice.number}).html
    assert "€10.00" in html and "€2.00" in html and "€12.10" not in html


def test_a_line_without_a_discount_has_none_and_its_price_is_without_vat(
    issuer, shelf, charge
):
    charge("inv-0023", [{"product": "SHA", "quantity": "3"}, {"product": "MNU"}])
    ticket = deliver("sale.sale.completed").invoice
    assert [
        (line.unit_price, line.discount_amount, line.base_amount) for line in ticket.lines
    ] == [(Decimal("1000.00"), 0, 3000), (Decimal("1000.00"), 0, 1000)]


def test_every_document_of_a_sale_says_what_the_operation_is(issuer, shelf, charge):
    # VeriFactu's DescripcionOperacion, mandatory in every record: the sale, in the AEAT's language.
    sale = charge("inv-0024")
    ticket = deliver("sale.sale.completed").invoice
    assert ticket.description == f"Venta {sale.number}"
    full = run(
        "invoice.invoice.substitute", {"number": ticket.number, **RECIPIENT}
    ).invoice
    assert full.description == f"Venta {sale.number}"


def test_the_issued_notice_says_where_the_document_comes_from(issuer, shelf, charge):
    # Sales links a document issued later by the outbox (a pending one) to its charge, refund or void.
    from live.models import OutboxEvent

    sold = charge("inv-0030", [{"product": "SHA"}, {"product": "WAX"}])
    voided = charge("inv-0031")
    refund(sold, 605, reason="Wax broken")
    run("sale.sale.void", {"sale_id": str(voided.id), "reason": "Wrong table"})
    deliver("sale.sale.voided")
    issued = [
        event.payload["source"]
        for event in OutboxEvent.objects.filter(name="invoice.invoice.issued").order_by(
            "created_at", "id"
        )
    ]
    refund_id = str(Sale.objects.get(pk=sold.id).refunds.get().id)
    assert {
        (item["type"], item["sale_id"], item["refund_id"], item["void"]) for item in issued
    } >= {
        ("sale", str(sold.id), None, False),
        ("sale", str(voided.id), None, False),
        ("refund", str(sold.id), refund_id, False),
        ("void", str(voided.id), None, True),
    }



# A sale line whose rule is gone (TAX-F11, pm#629 VF-17): declared with the tax family of the territory the line
# was charged in, as the line froze it, never a fixed VAT; nor the business's territory of today.


@pytest.mark.parametrize(
    ("region", "rule", "tax", "code"),
    [
        (None, None, "vat", "01"),
        ("ES-CN", {"rate_pct": "7", "tax_type": "igic"}, "igic", "03"),
        ("ES-CE", {"rate_pct": "4", "tax_type": "ipsi"}, "ipsi", "02"),
    ],
)
def test_a_sale_line_without_its_rule_keeps_the_tax_of_its_territory(product, charge, region, rule, tax, code):
    if rule:
        run(
            "tax.rule.create",
            {"country_code": "ES", "region_code": region, "tax_category_key": "product.generic", **rule},
        )
    run("tax.settings.update", {"region_code": region})
    product("Shirt", "SHI", 1210, "product.generic")
    # Charged before the business has its issuer: the till keeps the document pending.
    sale = charge("inv-region-0001", [{"product": "SHI"}])
    assert not Invoice.objects.filter(source_sale_id=sale.id).exists()
    SaleLine.objects.filter(sale_id=sale.id).update(tax_rule_id=None)
    # The business moves territory afterwards: the line keeps the one it was charged in.
    run("tax.settings.update", {"region_code": None if region else "ES-CN"})
    run("invoice.issuer.update", ISSUER)
    ticket = run("invoice.invoice.create_from_sale", {"sale_id": str(sale.id)}).invoice
    assert [entry.tax for entry in ticket.tax_breakdown] == [tax]
    record = Record.objects.get(invoice_id=ticket.id)
    assert re.findall(r"<sum1:Impuesto>(\d+)</sum1:Impuesto>", record.xml) == [code]
