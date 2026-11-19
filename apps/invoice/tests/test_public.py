"""The customer asks for the full invoice of their ticket with its code (INVOICE-F04), through the hub's public door,
without a session: ``invoice.public.ticket`` reads what the code opens and ``invoice.public.substitute`` issues, as the
system, the full invoice (F3) that replaces the ticket — Invoicing's own ``invoice.invoice.substitute``, once."""

import datetime as dt
import json

import pytest
from django.test import Client
from live.context import system_context

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import HUB_DB, ISSUER, run
from apps.sale.models import Sale
from apps.sale.queries.receipt_codes import CODE_LIFETIME, receipt_code
from apps.verifactu.chain import QR_HOSTS, TESTING
from apps.verifactu.models import Config, Record
from base.tenancy.context import use_hub
from base.tenancy.tests.business import HOST, A, B

pytestmark = [HUB_DB, pytest.mark.usefixtures("spa_manifest", "hub_a", "hub_b")]

B_HOST = f"{B.key}.localhost"
CUSTOMER = {
    "customer_name": "Carpintería Lema SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Mayor 1, 28001 Madrid",
}
UNKNOWN = "20200101-0001-K7Q2M9XD3FPA"


def door(operation: str, data: dict, *, host: str = HOST, slug: str = A.key, address: str = "203.0.113.7"):
    """A call of the page through the door, as its script makes it, from one connection of the customer's."""
    return Client().post(
        f"/p/{slug}/api/{operation}",
        json.dumps(data),
        content_type="application/json",
        HTTP_HOST=host,
        REMOTE_ADDR=address,
    )


def charge(key: str, scope=A) -> Sale:
    data = {"idempotency_key": key, "lines": [{"product": "SHA"}], "payments": [{"method": "card"}]}
    return Sale.objects.get(pk=run("sale.sale.complete", data, system_context(scope)).id)


@pytest.fixture
def shampoo(db):
    shampoo = {"name": "Shampoo", "sku": "SHA", "price": 1210, "tax_category_key": "product.generic"}
    run("inventory.product.create", shampoo, system_context(A))


@pytest.fixture
def ticket(issuer, shampoo) -> Sale:
    sale = charge("public-invoice-0001")
    assert sale.invoice_type == "F2"
    return sale


def full_invoices_of(sale: Sale) -> list[Invoice]:
    return list(Invoice.objects.filter(substitutes_id=sale.invoice_id))


def test_the_code_opens_its_ticket_without_a_session(ticket):
    response = door("invoice.public.ticket", {"code": receipt_code(ticket)})
    assert response.status_code == 200, response.content
    answer = response.json()
    assert answer["ticket"] == {
        "number": ticket.invoice_number,
        "issue_date": Invoice.objects.get(pk=ticket.invoice_id).issue_date.isoformat(),
        "total_amount": 1210,
        "currency": "EUR",
        "issuer_name": ISSUER["legal_name"],
    }
    assert answer["invoice"] is None


def test_the_customer_gets_the_full_invoice_that_replaces_the_ticket(ticket):
    response = door("invoice.public.substitute", {"code": receipt_code(ticket), **CUSTOMER})
    assert response.status_code == 200, response.content
    answer = response.json()
    full = answer["invoice"]
    assert (answer["issued"], answer["already"]) == (True, False)
    assert (full["invoice_type"], full["series_code"], full["customer_name"]) == ("F3", "FACT", CUSTOMER["customer_name"])
    assert full["substitutes"]["number"] == ticket.invoice_number
    assert full["total_amount"] == 1210
    assert [str(invoice.id) for invoice in full_invoices_of(ticket)] == [full["id"]]
    reread = door("invoice.public.ticket", {"code": receipt_code(ticket)}).json()
    assert reread["invoice"]["number"] == full["number"]


def test_asking_twice_answers_the_same_full_invoice_without_spending_a_number(ticket):
    code = receipt_code(ticket)
    first = door("invoice.public.substitute", {"code": code, **CUSTOMER}).json()
    numbers = list(InvoiceSeries.objects.values_list("code", "current_number"))
    again = door("invoice.public.substitute", {"code": code, **CUSTOMER, "customer_name": "Otra SL"})
    assert again.status_code == 200, again.content
    answer = again.json()
    assert (answer["issued"], answer["already"]) == (False, True)
    assert (answer["invoice"]["id"], answer["invoice"]["customer_name"]) == (first["invoice"]["id"], CUSTOMER["customer_name"])
    assert len(full_invoices_of(ticket)) == 1
    assert list(InvoiceSeries.objects.values_list("code", "current_number")) == numbers


@pytest.mark.parametrize("operation", ["invoice.public.ticket", "invoice.public.substitute"])
def test_a_code_that_opens_nothing_says_so_with_nobody_s_data(ticket, operation):
    code = receipt_code(ticket)
    forged = code[:-1] + ("2" if code[-1] != "2" else "3")
    for wrong in (UNKNOWN, forged):
        response = door(operation, {"code": wrong, **CUSTOMER})
        assert response.status_code == 404, response.content
        assert response.json()["error"]["code"] == "invoice.code_not_found"
        for private in (ticket.invoice_number, ticket.number, ISSUER["legal_name"], "12,10", "1210"):
            assert private not in response.content.decode()
    assert full_invoices_of(ticket) == []


def test_another_business_code_opens_nothing_here(ticket, hub_b):
    with use_hub(hub_b):
        run("invoice.issuer.update", ISSUER, system_context(B))
        shampoo = {"name": "Shampoo", "sku": "SHA", "price": 1210, "tax_category_key": "product.generic"}
        run("inventory.product.create", shampoo, system_context(B))
        theirs = charge("public-invoice-0001", scope=B)
    assert theirs.number == ticket.number
    response = door("invoice.public.substitute", {"code": receipt_code(theirs), **CUSTOMER})
    assert (response.status_code, response.json()["error"]["code"]) == (404, "invoice.code_not_found")
    assert full_invoices_of(ticket) == []
    with use_hub(hub_b):
        assert full_invoices_of(theirs) == []
    elsewhere = door("invoice.public.ticket", {"code": receipt_code(ticket)}, host=B_HOST, slug=B.key)
    assert elsewhere.status_code == 404


def test_an_expired_code_says_so_and_issues_nothing(ticket):
    Sale.objects.filter(pk=ticket.pk).update(created_at=ticket.created_at - CODE_LIFETIME - dt.timedelta(days=1))
    for operation in ("invoice.public.ticket", "invoice.public.substitute"):
        response = door(operation, {"code": receipt_code(ticket), **CUSTOMER})
        assert (response.status_code, response.json()["error"]["code"]) == (410, "invoice.code_expired"), response.content
        assert ticket.invoice_number not in response.content.decode()
    assert full_invoices_of(ticket) == []


def test_ten_codes_that_open_nothing_lock_that_connection_for_an_hour(ticket):
    for _ in range(10):
        assert door("invoice.public.ticket", {"code": UNKNOWN}).status_code == 404
    locked = door("invoice.public.substitute", {"code": receipt_code(ticket), **CUSTOMER})
    assert (locked.status_code, locked.json()["error"]["code"]) == (429, "base.rate_limited")
    assert full_invoices_of(ticket) == []
    other = door("invoice.public.substitute", {"code": receipt_code(ticket), **CUSTOMER}, address="198.51.100.4")
    assert other.status_code == 200, other.content


def test_a_right_code_is_never_counted(ticket):
    for _ in range(12):
        assert door("invoice.public.ticket", {"code": receipt_code(ticket)}).status_code == 200
    assert door("invoice.public.ticket", {"code": UNKNOWN}).status_code == 404


def test_a_ticket_still_without_its_fiscal_document_waits(shampoo):
    sale = charge("public-invoice-0002")
    assert sale.invoice_status == "pending"
    response = door("invoice.public.substitute", {"code": receipt_code(sale), **CUSTOMER})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "invoice.ticket_pending")


def test_the_customer_s_details_are_checked_as_at_the_counter(ticket):
    response = door("invoice.public.substitute", {"code": receipt_code(ticket), **CUSTOMER, "customer_tax_id": "B12345670"})
    assert response.status_code == 422, response.content
    assert set(response.json()["error"]["fields"]) == {"customer_tax_id"}
    incomplete = door("invoice.public.substitute", {"code": receipt_code(ticket), "customer_name": "Lema"})
    assert (incomplete.status_code, incomplete.json()["error"]["code"]) == (409, "invoice.recipient_incomplete")
    assert set(incomplete.json()["error"]["fields"]) == {"customer_tax_id", "customer_address"}
    assert full_invoices_of(ticket) == []


def test_the_full_invoice_is_sealed_for_the_aeat_test_environment_only(ticket):
    assert (Config.objects.filter(singleton=True).first() or Config()).environment == TESTING
    answer = door("invoice.public.substitute", {"code": receipt_code(ticket), **CUSTOMER}).json()
    record = Record.objects.get(invoice_id=answer["invoice"]["id"], record_type="alta", correction=False)
    assert record.environment == TESTING
    assert record.qr_url.startswith(QR_HOSTS[TESTING] + "/")
    assert answer["record"]["qr_url"] == record.qr_url
    assert answer["record"]["qr_svg"].startswith("data:image/svg+xml;base64,")


def test_the_page_of_the_code_is_the_shell_for_a_visitor_without_a_session(ticket):
    page = Client().get(f"/p/{A.key}/invoice/{receipt_code(ticket)}", HTTP_HOST=HOST, HTTP_ACCEPT="text/html")
    assert page.status_code == 200
    assert ticket.invoice_number not in page.content.decode()
    elsewhere = Client().get(f"/p/{B.key}/invoice/{receipt_code(ticket)}", HTTP_HOST=HOST, HTTP_ACCEPT="text/html")
    assert elsewhere.status_code == 404
