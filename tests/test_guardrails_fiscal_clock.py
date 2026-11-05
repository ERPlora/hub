"""What reaches the AEAT from a document issued at night in a business of another zone, frozen on what it receives today
(review of hub#771).

The issue date of an invoice, the day of a sale and Taxes' «today» are on the deployment's clock, and they move together
or not at all, under supervision (hub#772): the rate a «today» proposes or charges has to be the one in force on the date
the record says. A «today» moved alone changes the TipoImpositivo and the Huella of a record without anybody asking for
it, on the day a rate changes: the form proposes 10 % and the invoice goes out dated the day of the 21 %. Only hub#772
rewrites these tables, on purpose. The records are sealed, never sent: nothing here leaves the machine.
"""

import datetime as dt
import re
import socket
from typing import NamedTuple

import pytest
from django.utils import timezone

from apps.invoice.models import Invoice
from apps.tax.models import TaxCategory, TaxRule
from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import run
from base.models import Hub
from base.tenancy.context import use_hub

pytestmark = pytest.mark.django_db

ISSUER = {
    "legal_name": "Peluquería Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, Madrid",
}

#: The hours the business, Madrid and UTC disagree on the day, in both directions, and Madrid's as the control.
BOGOTA = ("America/Bogota", dt.datetime(2026, 11, 3, 4, 30, tzinfo=dt.UTC))  # 23:30 of the 2nd there, the 3rd in Madrid
CANARY = ("Atlantic/Canary", dt.datetime(2026, 11, 2, 23, 30, tzinfo=dt.UTC))  # 23:30 of the 2nd there, the 3rd in Madrid
TOKYO_NIGHT = ("Asia/Tokyo", dt.datetime(2026, 11, 2, 14, 30, tzinfo=dt.UTC))  # 23:30 of the 2nd, and in Madrid
TOKYO_MORNING = ("Asia/Tokyo", dt.datetime(2026, 11, 2, 15, 30, tzinfo=dt.UTC))  # 00:30 of the 3rd there, the 2nd in Madrid
MADRID = ("Europe/Madrid", dt.datetime(2026, 11, 2, 22, 30, tzinfo=dt.UTC))  # 23:30 of the 2nd


class Sent(NamedTuple):
    """What the record says, as its XML says it."""

    FechaExpedicionFactura: str
    DescripcionOperacion: str
    TipoImpositivo: str
    CuotaTotal: str
    ImporteTotal: str
    FechaHoraHusoGenRegistro: str
    Huella: str


SALE_OF_THE_3RD = ("03-11-2026", "Venta 20261103-0001", "21.00", "1.74", "10.00")
SALE_OF_THE_2ND = ("02-11-2026", "Venta 20261102-0001", "10.00", "0.91", "10.00")
INVOICE_OF_THE_3RD = ("03-11-2026", "Course", "21.00", "2.10", "12.10")
INVOICE_OF_THE_2ND = ("02-11-2026", "Course", "10.00", "1.00", "11.00")

SALES = [
    pytest.param(
        BOGOTA,
        Sent(*SALE_OF_THE_3RD, "2026-11-03T05:30:00+01:00", "8B07FB386689F40651B358A7DD80C9A8084B60321D362DD986D9FDAB0D353D38"),
        id="bogota-2330",
    ),
    pytest.param(
        CANARY,
        Sent(*SALE_OF_THE_3RD, "2026-11-03T00:30:00+01:00", "71DB83BE150F194294F02949187D3729DF1544730430160ADAB444455B1635AE"),
        id="canary-2330",
    ),
    pytest.param(
        TOKYO_NIGHT,
        Sent(*SALE_OF_THE_2ND, "2026-11-02T15:30:00+01:00", "B1EC9B4B856B3E37A6CA6B5A7660F74591EC742058E74C540C50E0A249F81739"),
        id="tokyo-2330",
    ),
    pytest.param(
        TOKYO_MORNING,
        Sent(*SALE_OF_THE_2ND, "2026-11-02T16:30:00+01:00", "5F59845034F5C290CB760E7B522603AF7B3F301B73EC2845057F1FA3AD33EA77"),
        id="tokyo-0030",
    ),
    pytest.param(
        MADRID,
        Sent(*SALE_OF_THE_2ND, "2026-11-02T23:30:00+01:00", "4AAD6B004C6E86EBB69866238108C12BC6507CC87CC3D647A2B313C2DB9EB3EA"),
        id="madrid-2330",
    ),
]
INVOICES = [
    pytest.param(
        BOGOTA,
        Sent(*INVOICE_OF_THE_3RD, "2026-11-03T05:30:00+01:00", "A545C1B73900F56E957AB494D4BA53BFA4AB8457E1408B091E8E6BB1E437D899"),
        id="bogota-2330",
    ),
    pytest.param(
        CANARY,
        Sent(*INVOICE_OF_THE_3RD, "2026-11-03T00:30:00+01:00", "383FB438E5AB9EB792A18E28B09C0B85C4F6910CEB679DBF2B3FEDD28C0A1FAF"),
        id="canary-2330",
    ),
    pytest.param(
        TOKYO_NIGHT,
        Sent(*INVOICE_OF_THE_2ND, "2026-11-02T15:30:00+01:00", "1FBC16CB19052777AFC320549648E1DCD9A032A80B6B18EDAADFE6476FFA76E9"),
        id="tokyo-2330",
    ),
    pytest.param(
        TOKYO_MORNING,
        Sent(*INVOICE_OF_THE_2ND, "2026-11-02T16:30:00+01:00", "F77A2B2A27D6941E51014CA94B4C01EEB20C1CDF5C2F4E94D0181315B5768460"),
        id="tokyo-0030",
    ),
    pytest.param(
        MADRID,
        Sent(*INVOICE_OF_THE_2ND, "2026-11-02T23:30:00+01:00", "F7DB497806B59FF480F7B27280217F1DE2D52CC56C09A15C670A6B51AC81D47A"),
        id="madrid-2330",
    ),
]


def sent(invoice: Invoice) -> Sent:
    record = Record.objects.get(invoice=invoice)
    assert record.environment == "testing"
    # The operation is on the day of the issue, so the record does not say it apart.
    assert "FechaOperacion" not in record.xml
    return Sent(*(re.findall(rf"<(?:\w+:)?{tag}>([^<]*)</", record.xml)[0] for tag in Sent._fields))


@pytest.fixture(autouse=True)
def nothing_leaves(monkeypatch):
    real = socket.socket.connect

    def connect(self, address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"tried to connect to {address}")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture(autouse=True)
def rate_turns_at_midnight(db):
    """The issuer, and a general rate that changes at the turn of the night: 10 % until the 2nd, 21 % from the 3rd."""
    run("invoice.issuer.update", ISSUER)
    category = TaxCategory.objects.get(key="product.generic")
    TaxRule.objects.filter(category=category).delete()
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="10", valid_to=dt.date(2026, 11, 2))
    TaxRule.objects.create(category=category, country_code="ES", rate_pct="21", valid_from=dt.date(2026, 11, 3))


@pytest.mark.parametrize(("moment", "expected"), SALES)
def test_a_sale_at_night_reaches_the_record_as_frozen(monkeypatch, moment, expected):
    zone, instant = moment
    run("inventory.product.create", {"name": "Shampoo", "sku": "SHA", "price": 1000, "tax_category_key": "product.generic"})
    monkeypatch.setattr(timezone, "now", lambda: instant)
    with use_hub(Hub(slug="a", timezone=zone)):
        sale = run(
            "sale.sale.complete",
            {
                "idempotency_key": "019a0000-0000-7000-8000-000000000001",
                "lines": [{"product": "SHA"}],
                "payments": [{"method": "card"}],
            },
        )
    assert sent(Invoice.objects.get(source_sale_id=sale.id)) == expected


@pytest.mark.parametrize(("moment", "expected"), INVOICES)
def test_an_invoice_at_the_rate_the_form_proposes_reaches_the_record_as_frozen(monkeypatch, moment, expected):
    zone, instant = moment
    monkeypatch.setattr(timezone, "now", lambda: instant)
    with use_hub(Hub(slug="a", timezone=zone)):
        proposed = run("invoice.invoice.line_defaults").tax_rate
        created = run(
            "invoice.invoice.create",
            {
                "lines": [{"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": str(proposed)}],
                **RECIPIENT,
            },
        )
    assert sent(Invoice.objects.get(pk=created.id)) == expected
