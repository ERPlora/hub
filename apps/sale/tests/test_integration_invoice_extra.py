"""What another app adds to a tender (SALE-F39, the tip) never reaches the fiscal chain: the ticket or invoice that
Invoicing issues from a sale with it, and its VeriFactu registration record, declare the same base, tax and total as
the very same sale without it. Sale, Invoicing and VeriFactu together, no mocks; nothing is sent to the AEAT here.
"""

import re

import pytest

from apps.invoice.models import Invoice
from apps.sale.tests.conftest import HUB_DB, run
from apps.sale.tests.test_integration_invoice import RECIPIENT, issuer
from apps.verifactu.models import Record

pytestmark = [HUB_DB, pytest.mark.usefixtures("a_step_at_the_charge")]

#: The issuer fixture of the invoice integration tests: the business's tax identity, as the owner sets it.
__all__ = ["issuer"]

TIPPED = [{"method": "cash", "tendered": 5000, "extra": 500, "extra_label": "Tip"}]
PLAIN = [{"method": "cash", "tendered": 5000}]


@pytest.fixture(autouse=True)
def menu(product):
    product("Steak", "STK", 1800, "restaurant.food")
    product("Wine", "WIN", 2290, "restaurant.drink")


def charge(key: str, payments: list[dict], **more):
    return run(
        "sale.sale.complete",
        {
            "idempotency_key": key,
            "lines": [{"product": "STK"}, {"product": "WIN"}],
            "payments": payments,
            **more,
        },
    )


def declared(sale) -> tuple:
    """What the fiscal document and its record say of a sale: everything but its number, date and chain."""
    invoice = Invoice.objects.get(source_sale_id=sale.id)
    record = Record.objects.get(invoice_id=invoice.id)
    lines = [
        (line.description, line.quantity, line.unit_price, line.tax_rate, line.base_amount, line.tax_amount)
        for line in invoice.lines.order_by("position")
    ]
    return (
        (invoice.invoice_type, invoice.base_amount, invoice.tax_amount, invoice.total_amount, invoice.tax_breakdown),
        lines,
        (record.base_amount, record.tax_amount, record.total_amount, record.tax_breakdown),
        re.findall(r"<sum1:(ImporteTotal|CuotaTotal|BaseImponibleOimporteNoSujeto)>([^<]+)<", record.xml),
    )


@pytest.mark.parametrize("document", [{}, {"document_type": "invoice", **RECIPIENT}])
def test_the_ticket_or_invoice_and_its_record_are_those_of_the_sale_without_what_is_added(issuer, document):
    tipped = charge("fiscal-extra-0001", TIPPED, **document)
    plain = charge("fiscal-extra-0002", PLAIN, **document)
    assert (tipped.subtotal, tipped.tax_total, tipped.total) == (plain.subtotal, plain.tax_total, plain.total)
    assert [(row.rate_pct, row.base, row.tax) for row in tipped.breakdown] == [
        (row.rate_pct, row.base, row.tax) for row in plain.breakdown
    ]
    assert tipped.invoice_status == plain.invoice_status == "issued"
    assert declared(tipped) == declared(plain)
    assert declared(tipped)[0][3] == 4090
