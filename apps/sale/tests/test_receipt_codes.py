"""The code a ticket carries for its customer to ask for its full invoice (INVOICE-F04): made from the sale itself, never
stored, and opening that sale of this business only."""

import datetime as dt

import pytest
from django.test import override_settings
from django.utils import timezone
from live.context import system_context

from apps.sale.models.sales import Sale
from apps.sale.queries.receipt_codes import CODE_LIFETIME, expired, receipt_code, sale_of_code
from apps.sale.tests.conftest import HUB_DB, B, ctx_for, run
from base.tenancy.context import use_hub

pytestmark = HUB_DB

CROCKFORD = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
INVOICE_RECIPIENT = {
    "customer_name": "Carpintería Lema SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Mayor 1, Madrid",
}


def charge(key: str, ctx=None, **more) -> Sale:
    data = {"idempotency_key": key, "lines": [{"product": "COF"}], "payments": [{"method": "card"}], **more}
    return Sale.objects.get(pk=run("sale.sale.complete", data, ctx).id)


@pytest.fixture
def ticket(product):
    product()
    return charge("receipt-code-0001")


def test_a_ticket_has_a_code_made_of_its_number_and_a_signature(ticket):
    code = receipt_code(ticket)
    number, signature = code.rsplit("-", 1)
    assert number == ticket.number
    assert len(signature) == 12
    assert set(signature) <= CROCKFORD
    assert receipt_code(Sale.objects.get(pk=ticket.pk)) == code


def test_a_sale_charged_as_an_invoice_has_no_code(product):
    product()
    sale = charge("receipt-code-0002", document_type="invoice", **INVOICE_RECIPIENT)
    assert receipt_code(sale) is None
    forged = f"{sale.number}-{receipt_code(charge('receipt-code-0003')).rsplit('-', 1)[1]}"
    assert sale_of_code(forged) is None


def test_the_code_opens_its_sale_also_typed_by_hand(ticket):
    code = receipt_code(ticket)
    assert sale_of_code(code) == ticket
    typed = code.lower().replace("0", "o").replace("1", "l")
    assert sale_of_code(f"  {typed} ") == ticket


@pytest.mark.parametrize("change", ["signature", "number", "accented", "garbage", "empty"])
def test_a_code_nobody_made_opens_nothing(ticket, change):
    code = receipt_code(ticket)
    number, signature = code.rsplit("-", 1)
    flipped = ("1" if signature[0] != "1" else "2") + signature[1:]
    other = {
        "signature": f"{number}-{flipped}",
        "number": f"20200101-0001-{signature}",
        "accented": f"{number}-{signature[:-1]}Ñ",
        "garbage": "not-a-code",
        "empty": "",
    }[change]
    assert sale_of_code(other) is None


def test_a_code_signed_before_the_key_changed_still_opens(ticket, settings):
    code = receipt_code(ticket)
    with override_settings(SECRET_KEY="a new key", SECRET_KEY_FALLBACKS=[settings.SECRET_KEY]):
        assert sale_of_code(code) == ticket
        assert receipt_code(ticket) != code
    with override_settings(SECRET_KEY="a new key", SECRET_KEY_FALLBACKS=[]):
        assert sale_of_code(code) is None


def test_another_business_code_opens_nothing_here_even_with_the_same_number(ticket, hub_b):
    coffee = {"name": "Coffee", "sku": "COF", "price": 150, "tax_category_key": "restaurant.drink"}
    with use_hub(hub_b):
        run("inventory.product.create", coffee, system_context(B))
        theirs = charge("receipt-code-0001", ctx_for(scope=B))
        their_code = receipt_code(theirs)
    assert theirs.number == ticket.number
    assert sale_of_code(their_code) is None
    assert sale_of_code(receipt_code(ticket)) == ticket


def test_a_code_lasts_four_years_from_the_charge(ticket):
    assert CODE_LIFETIME == dt.timedelta(days=4 * 365 + 1)
    assert not expired(ticket, ticket.created_at + CODE_LIFETIME)
    assert expired(ticket, ticket.created_at + CODE_LIFETIME + dt.timedelta(seconds=1))
    assert not expired(ticket, timezone.now())
