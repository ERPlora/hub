"""An invoice issued by hand, for the tests that need one: issued, read again as it was kept, or refused."""

import datetime as dt

import pytest
from live.errors import Conflict

from apps.invoice.models import Invoice, InvoiceSeries
from apps.invoice.tests.conftest import ctx_for, run

RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3",
}
LINE = {"description": "Course", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}
HUNDRED = {**LINE, "unit_price": 10000}
#: Noon of 24 November in Madrid, for the ``at`` fixture.
NOON = ("Europe/Madrid", dt.datetime(2026, 11, 24, 11, 0, tzinfo=dt.UTC))


def manual(ctx=None, **more):
    """An invoice of 12.10 € in FACT, unless ``more`` says another thing."""
    return run("invoice.invoice.create", {"lines": [LINE], **RECIPIENT, **more}, ctx)


def line(price: int, rate="21") -> dict:
    return {**LINE, "unit_price": price, "tax_rate": rate}


def withheld(rate=15, *lines, **more):
    """An invoice of 100 € + 21 % VAT with that IRPF withholding, unless ``lines`` say another thing."""
    return manual(lines=list(lines) or [HUNDRED], withholding_rate=rate, **more)


def stored(answer) -> Invoice:
    return Invoice.objects.get(pk=answer.id)


def page(answer, language="en") -> str:
    """Its A4 page, as a person who reads ``language`` prints it."""
    return run("invoice.invoice.document", {"invoice_id": str(answer.id)}, ctx_for(language=language)).html


def refused(**data) -> Conflict:
    """The refusal of a manual invoice with ``data``: nothing is issued and no number is spent."""
    before = (Invoice.objects.count(), sum(InvoiceSeries.objects.values_list("current_number", flat=True)))
    with pytest.raises(Conflict) as error:
        manual(**data)
    after = (Invoice.objects.count(), sum(InvoiceSeries.objects.values_list("current_number", flat=True)))
    assert after == before
    return error.value
