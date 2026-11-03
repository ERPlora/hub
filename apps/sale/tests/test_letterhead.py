"""The business as the papers of the till name it (SALE-F21, SALE-F29; hub#458; RD 1619/2012 arts. 6 and 7): the
name, tax ID and address of Invoicing's issuer, with the receipt header added under them, never instead of them.
A sale with a fiscal document says what that document says, whatever the issuer becomes later. Real sales and the
real issuer, through their operations."""

import pytest
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied
from live.live_registry import live_registry

from apps.sale import events
from apps.sale.tests.conftest import A, B, ctx_for, run
from base.models import Hub

pytestmark = pytest.mark.django_db

ISSUER = {
    "legal_name": "Salón Aurora S.L.",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}
ADDRESS = "Calle Mayor 1, 28001 Madrid (Madrid)"


@pytest.fixture
def coffee(product):
    product("Coffee", "COF", 150, "restaurant.drink")


def charge(key="letterhead-1", **more):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "lines": [{"product": "COF", "quantity": "1"}], "payments": [{"method": "card"}], **more},
    )


def letterhead(sale_id=None, ctx=None):
    data = {"sale_id": str(sale_id)} if sale_id else {}
    return run("sale.letterhead.get", data, ctx).model_dump(mode="json")


def identity(sale_id=None, ctx=None):
    found = letterhead(sale_id, ctx)
    return found["name"], found["tax_id"], found["lines"]


def test_the_paper_names_the_issuer_and_the_receipt_header_goes_under_it():
    run("invoice.issuer.update", ISSUER)
    run("sale.settings.update", {"receipt_header": "Bar Aurora\nTel. 600 000 000"})
    assert letterhead() == {
        "sale_id": None,
        "name": "Salón Aurora S.L.",
        "tax_id": "B12345674",
        "lines": [ADDRESS, "Bar Aurora", "Tel. 600 000 000"],
    }


def test_a_header_that_repeats_the_issuer_does_not_print_it_twice():
    run("invoice.issuer.update", ISSUER)
    run("sale.settings.update", {"receipt_header": f"SALÓN AURORA S.L.\n{ADDRESS}\nTel. 600 000 000"})
    assert identity() == ("Salón Aurora S.L.", "B12345674", [ADDRESS, "Tel. 600 000 000"])


def test_without_an_issuer_the_header_names_the_business_as_before():
    run("sale.settings.update", {"receipt_header": "Bar Ana\nCalle Mayor 1\n28001 Madrid"})
    assert identity() == ("Bar Ana", "", ["Calle Mayor 1", "28001 Madrid"])


def test_without_issuer_or_header_it_is_the_name_the_business_registered():
    Hub.objects.update_or_create(slug=A.key, defaults={"name": "Salón Aurora"})
    assert identity() == ("Salón Aurora", "", [])


def test_my_business_only_when_there_is_no_name_to_read():
    Hub.objects.filter(slug=A.key).delete()
    assert identity(ctx=ctx_for(language="es")) == ("Mi negocio", "", [])


def test_a_sale_with_its_document_keeps_the_issuer_that_document_says(coffee):
    run("invoice.issuer.update", ISSUER)
    sale = charge()
    assert sale.invoice_id is not None
    run("invoice.issuer.update", {**ISSUER, "legal_name": "Aurora Nueva S.L.", "address": "Calle Real 2"})
    assert letterhead(sale.id) == {
        "sale_id": str(sale.id),
        "name": "Salón Aurora S.L.",
        "tax_id": "B12345674",
        "lines": [ADDRESS],
    }
    assert identity()[0] == "Aurora Nueva S.L."


def test_a_sale_whose_document_waits_names_the_issuer_of_today(coffee):
    sale = charge()
    assert sale.invoice_id is None
    run("invoice.issuer.update", ISSUER)
    assert identity(sale.id) == ("Salón Aurora S.L.", "B12345674", [ADDRESS])


def test_an_unknown_sale_is_not_found():
    with pytest.raises(NotFound):
        letterhead("019a0000-0000-7000-8000-000000000000")


def test_whoever_can_see_the_sales_reads_it_even_without_rights_over_invoicing(coffee):
    run("invoice.issuer.update", ISSUER)
    sale = charge()
    cashier = OperationContext(scope=A, actor="cashier", permissions=frozenset({"sale.view_sale"}))
    assert identity(ctx=cashier)[:2] == ("Salón Aurora S.L.", "B12345674")
    assert identity(sale.id, cashier)[:2] == ("Salón Aurora S.L.", "B12345674")
    with pytest.raises(PermissionDenied):
        letterhead(ctx=OperationContext(scope=A, actor="nobody", permissions=frozenset()))


def test_without_invoicing_the_paper_goes_with_the_header(monkeypatch):
    monkeypatch.setattr("apps.sale.queries.ISSUER", "invoice.issuer.not_installed")
    run("invoice.issuer.update", ISSUER)
    run("sale.settings.update", {"receipt_header": "Bar Ana"})
    assert identity() == ("Bar Ana", "", [])


def test_one_business_never_prints_the_issuer_of_another():
    run("invoice.issuer.update", ISSUER)
    Hub.objects.update_or_create(slug=B.key, defaults={"name": "Peluquería Beta"})
    in_b = ctx_for(scope=B)
    assert identity(ctx=in_b) == ("Peluquería Beta", "", [])
    assert identity()[1] == "B12345674"


def test_the_screen_paper_follows_the_issuer_the_header_and_the_sale():
    following = {
        event for event in [*events.SALE_EVENTS, events.SETTINGS_UPDATED, "invoice.issuer.updated"]
        if "sale.letterhead.get" in live_registry.affected([event])
    }
    assert following == {*events.SALE_EVENTS, events.SETTINGS_UPDATED, "invoice.issuer.updated"}


def test_a_full_invoice_keeps_its_recipient_for_the_paper_and_a_ticket_has_none(coffee):
    run("invoice.issuer.update", ISSUER)
    invoice = charge(
        "letterhead-invoice",
        document_type="invoice",
        customer_name="Javier Gomez Ruiz",
        customer_tax_id="76543210S",
        customer_address="Calle Real 2",
    )
    read = run("sale.sale.get", {"sale_id": str(invoice.id)})
    assert (read.customer_name, read.customer_tax_id, read.customer_address) == (
        "Javier Gomez Ruiz",
        "76543210S",
        "Calle Real 2",
    )
    ticket = run("sale.sale.get", {"sale_id": str(charge("letterhead-ticket").id)})
    assert (ticket.customer_tax_id, ticket.customer_address) == ("", "")
