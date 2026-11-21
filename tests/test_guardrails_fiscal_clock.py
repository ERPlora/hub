"""What reaches the AEAT from a document issued at night in a business of another zone, frozen on what it receives.

The issue date of an invoice, the day of a sale and Taxes' «today» are on the business's clock, and they move together:
the rate a «today» proposes or charges has to be the one in force on the date the record says, or the TipoImpositivo
and the Huella of a record change on the day a rate changes (the form proposes 10 % and the invoice goes out dated the
day of the 21 %). The hour a record is generated at is still the deployment's (Madrid). The records are sealed, never
sent: nothing here leaves the machine. The business is ``hub_a``, in its own database.
"""

import datetime as dt
import re
from typing import NamedTuple

import pytest
from django.utils import timezone

from apps.invoice.models import Invoice
from apps.tax.models import TaxCategory
from apps.tax.tests.conftest import turn_the_rate_at_midnight
from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import HUB_DB, run
from base.tenancy.context import use_hub
from control.models import Hub

pytestmark = [HUB_DB, pytest.mark.usefixtures("nothing_leaves")]

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
        Sent(*SALE_OF_THE_2ND, "2026-11-03T05:30:00+01:00", "4C8E8FB32085E9F6D963CC06A05579C986D8DA20A6A688B2C0422AB8D2856A7B"),
        id="bogota-2330",
    ),
    pytest.param(
        CANARY,
        Sent(*SALE_OF_THE_2ND, "2026-11-03T00:30:00+01:00", "5C33597617223FCD7D67528A27A331357410224922165D283516E12C3CEBD205"),
        id="canary-2330",
    ),
    pytest.param(
        TOKYO_NIGHT,
        Sent(*SALE_OF_THE_2ND, "2026-11-02T15:30:00+01:00", "B1EC9B4B856B3E37A6CA6B5A7660F74591EC742058E74C540C50E0A249F81739"),
        id="tokyo-2330",
    ),
    pytest.param(
        TOKYO_MORNING,
        Sent(*SALE_OF_THE_3RD, "2026-11-02T16:30:00+01:00", "26D3C9A99D7D55946CBB1D75C442F00317C2EBE66664347C80B39D07DA98E28F"),
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
        Sent(*INVOICE_OF_THE_2ND, "2026-11-03T05:30:00+01:00", "15EC87FB5B392C5CE2E956B4A43D59DC53ED797ABB49960960005F94BEA26C8E"),
        id="bogota-2330",
    ),
    pytest.param(
        CANARY,
        Sent(*INVOICE_OF_THE_2ND, "2026-11-03T00:30:00+01:00", "3BB8494A045563D73010970C45E381F88F717029175285FF67564FE68F6B3361"),
        id="canary-2330",
    ),
    pytest.param(
        TOKYO_NIGHT,
        Sent(*INVOICE_OF_THE_2ND, "2026-11-02T15:30:00+01:00", "1FBC16CB19052777AFC320549648E1DCD9A032A80B6B18EDAADFE6476FFA76E9"),
        id="tokyo-2330",
    ),
    pytest.param(
        TOKYO_MORNING,
        Sent(*INVOICE_OF_THE_3RD, "2026-11-02T16:30:00+01:00", "D0DBB34903547E965D900481593077EA5CC35B0F2070A51B08F79403D7DC418D"),
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
def business(hub_a):
    """The business ``A`` (``hub_a``), entered for the whole test."""
    with use_hub(hub_a):
        yield hub_a


def in_zone(business, zone: str):
    """The business, its zone now ``zone``: the clock its day is read on."""
    Hub.objects.filter(pk=business.pk).update(timezone=zone)
    return use_hub(Hub.objects.get(pk=business.pk))


@pytest.fixture(autouse=True)
def rate_turns_at_midnight(business):
    """The issuer, and a general rate that changes at the turn of the night: 10 % until the 2nd, 21 % from the 3rd."""
    run("invoice.issuer.update", ISSUER)
    turn_the_rate_at_midnight(TaxCategory.objects.get(key="product.generic"))


@pytest.mark.parametrize(("moment", "expected"), SALES)
def test_a_sale_at_night_reaches_the_record_as_frozen(business, monkeypatch, moment, expected):
    zone, instant = moment
    run("inventory.product.create", {"name": "Shampoo", "sku": "SHA", "price": 1000, "tax_category_key": "product.generic"})
    monkeypatch.setattr(timezone, "now", lambda: instant)
    with in_zone(business, zone):
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
def test_an_invoice_at_the_rate_the_form_proposes_reaches_the_record_as_frozen(business, monkeypatch, moment, expected):
    zone, instant = moment
    monkeypatch.setattr(timezone, "now", lambda: instant)
    with in_zone(business, zone):
        proposed = run("invoice.invoice.line_defaults").tax_rate
        created = run(
            "invoice.invoice.create",
            {
                "lines": [{"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": str(proposed)}],
                **RECIPIENT,
            },
        )
    assert sent(Invoice.objects.get(pk=created.id)) == expected
