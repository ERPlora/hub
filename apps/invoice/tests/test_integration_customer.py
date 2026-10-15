"""Invoicing and Customers together, no mocks (INVOICE-F02, F03, F05): the recipient of a full invoice is
copied from a real customer card (by its id or, for voice, by its exact name, phone or email), checked, and
never changes when the card does afterwards.
"""

import pytest
from live.errors import InvalidPayload, NotFound

from apps.invoice.tests.conftest import ISSUER, deliver, run

pytestmark = pytest.mark.django_db

LINE = {
    "description": "Hair course",
    "quantity": "1",
    "unit_price": 10000,
    "tax_rate": "21",
}


@pytest.fixture
def card(customer):
    return customer(
        "Ana López",
        company_name="Estudio Ana SL",
        tax_id="B12345674",
        address="Calle Sol 5",
        postal_code="28013",
        city="Madrid",
    )


def test_a_manual_invoice_takes_the_recipient_from_the_card(issuer, card):
    invoice = run(
        "invoice.invoice.create", {"customer_id": str(card.id), "lines": [LINE]}
    )
    assert (
        invoice.customer_id,
        invoice.customer_name,
        invoice.customer_tax_id,
        invoice.customer_address,
    ) == (
        card.id,
        "Estudio Ana SL",
        "B12345674",
        "Calle Sol 5, 28013 Madrid",
    )


def test_a_card_is_named_by_voice_and_what_is_typed_wins(issuer, card):
    invoice = run(
        "invoice.invoice.create",
        {"customer": "ana lópez", "customer_address": "Otra calle 1", "lines": [LINE]},
    )
    assert (invoice.customer_id, invoice.customer_address) == (card.id, "Otra calle 1")
    with pytest.raises(NotFound):
        run("invoice.invoice.create", {"customer": "Nobody", "lines": [LINE]})


def test_a_tax_id_of_the_card_that_does_not_check_is_refused_under_its_field(
    issuer, customer
):
    wrong = customer("Luis", tax_id="B12345678", address="Calle 1")
    with pytest.raises(InvalidPayload) as refused:
        run("invoice.invoice.create", {"customer_id": str(wrong.id), "lines": [LINE]})
    assert set(refused.value.fields) == {"customer_tax_id"}


def test_editing_the_card_afterwards_never_changes_an_issued_invoice(issuer, card):
    invoice = run(
        "invoice.invoice.create", {"customer_id": str(card.id), "lines": [LINE]}
    )
    run(
        "customer.customer.update",
        {"id": str(card.id), "company_name": "Otro SL", "tax_id": "12345678Z"},
    )
    again = run("invoice.invoice.get", {"invoice_id": str(invoice.id)})
    assert (again.customer_name, again.customer_tax_id) == (
        "Estudio Ana SL",
        "B12345674",
    )


def test_a_foreign_card_is_declared_by_its_country(issuer, customer):
    french = customer(
        "Jean", tax_id="FR40303265045", address="Rue 1", city="Paris", country="FR"
    )
    invoice = run(
        "invoice.invoice.create",
        {"customer_id": str(french.id), "customer_id_type": "02", "lines": [LINE]},
    )
    assert (
        invoice.customer_country,
        invoice.customer_id_type,
        invoice.customer_tax_id,
    ) == ("FR", "02", "FR40303265045")


def test_a_ticket_is_replaced_by_the_full_invoice_of_a_card(
    issuer, product, charge, card
):
    product()
    charge("cust-0001")
    ticket = deliver("sale.sale.completed").invoice
    full = run(
        "invoice.invoice.substitute",
        {"number": ticket.number, "customer_id": str(card.id)},
    ).invoice
    assert (full.invoice_type, full.customer_name, full.customer_tax_id) == (
        "F3",
        "Estudio Ana SL",
        "B12345674",
    )


def test_a_sale_of_a_card_carries_it_to_its_ticket_and_its_invoice(
    issuer, product, charge, card
):
    product()
    charge("cust-0002", customer_id=str(card.id))
    ticket = deliver("sale.sale.completed").invoice
    # A ticket's recipient is its card, read by Invoicing: its fiscal name (the company's, when it has one).
    assert (ticket.invoice_type, ticket.customer_id, ticket.customer_name) == (
        "F2",
        card.id,
        "Estudio Ana SL",
    )
    charge("cust-0003", customer_id=str(card.id), document_type="invoice")
    invoice = deliver("sale.sale.completed").invoice
    # The sale took the recipient from the card when it was charged: the invoice copies it.
    assert (
        invoice.invoice_type,
        invoice.customer_id,
        invoice.customer_tax_id,
        invoice.customer_address,
    ) == (
        "F1",
        card.id,
        "B12345674",
        "Calle Sol 5, 28013 Madrid",
    )


def test_a_ticket_is_issued_without_a_tax_id_of_the_card_that_does_not_check(
    product, charge, customer
):
    # A simplified invoice needs no recipient: a wrong tax ID on the card never leaves the ticket pending.
    # Charged before the issuer exists, the outbox's payload (which carries that tax ID) issues it later.
    product()
    wrong = customer("Luis Pérez", tax_id="12345678A", address="Calle 1")
    charge("cust-0009", customer_id=str(wrong.id))
    run("invoice.issuer.update", ISSUER)
    ticket = deliver("sale.sale.completed").invoice
    assert (
        ticket.invoice_type,
        ticket.customer_id,
        ticket.customer_name,
        ticket.customer_tax_id,
        ticket.customer_id_type,
    ) == ("F2", wrong.id, "Luis Pérez", "", "")


def test_a_full_invoice_of_a_sale_still_needs_a_tax_id_that_checks(product, charge):
    product()
    sale = charge(
        "cust-0010",
        document_type="invoice",
        customer_name="Talleres Pérez SL",
        customer_tax_id="B12345674",
        customer_address="Calle Luna 3",
    )
    run("invoice.issuer.update", ISSUER)
    for body, field in (
        ({"customer_tax_id": "12345678A"}, "customer_tax_id"),
        ({"customer_tax_id": "P1234567", "customer_country": "US"}, "customer_id_type"),
    ):
        with pytest.raises(InvalidPayload) as refused:
            run("invoice.invoice.create_from_sale", {"sale_id": str(sale.id), **body})
        assert set(refused.value.fields) == {field}



def test_a_card_whose_name_does_not_fit_verifactu_is_refused_under_its_field(
    issuer, customer
):
    # NombreRazon holds 120 characters (SuministroInformacion.xsd); a card may hold 200.
    long = customer("Ana", company_name="E" * 130, tax_id="B12345674", address="Calle 1")
    with pytest.raises(InvalidPayload) as refused:
        run("invoice.invoice.create", {"customer_id": str(long.id), "lines": [LINE]})
    assert set(refused.value.fields) == {"customer_name"}


def test_a_ticket_of_a_card_whose_name_does_not_fit_goes_without_it(
    issuer, customer
):
    long = customer("Ana", company_name="E" * 130)
    ticket = run(
        "invoice.invoice.create",
        {"series_code": "TICKET", "customer_id": str(long.id), "lines": [LINE]},
    )
    assert (ticket.invoice_type, ticket.customer_id, ticket.customer_name) == (
        "F2",
        long.id,
        "",
    )
