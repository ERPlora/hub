"""Models of the invoice app: what the database itself refuses, whatever door a row comes through.

A fiscal document is unique by its number in its series, its sequence in its series, one per sale, one
per refund, one per void and one substitute per ticket; its total is base + tax; an ordinary document
is never negative and a rectifying one never positive. A series is unique by code and year, and a year
has at most one default series. The issuer is a single row.
"""

import datetime as dt
import pytest
from django.db import IntegrityError, transaction
from django.utils import translation

from apps.invoice.models import Invoice, InvoiceLine, InvoiceSeries, Issuer

pytestmark = pytest.mark.django_db

TODAY = dt.date(2026, 10, 14)


def series(code="FACT", year=2026, invoice_type="F1", **more):
    return InvoiceSeries.objects.create(
        code=code, year=year, invoice_type=invoice_type, prefix=code, **more
    )


def document(
    serie, sequence=1, number=None, invoice_type=None, base=1000, tax=210, **more
):
    more.setdefault("total_amount", base + tax)
    return Invoice.objects.create(
        series=serie,
        series_code=serie.code,
        year=serie.year,
        sequence=sequence,
        number=number or f"{serie.prefix}-{serie.year}-{sequence:06d}",
        invoice_type=invoice_type or serie.invoice_type,
        issue_date=TODAY,
        operation_date=TODAY,
        base_amount=base,
        tax_amount=tax,
        **more,
    )


def a_sale(number="20261014-0001"):
    """A bare charged sale (the foreign keys need a real row; the operations are tested elsewhere)."""
    from apps.sale.models import Sale

    return Sale.objects.create(
        number=number,
        business_day=TODAY,
        sequence=int(number[-4:]),
        idempotency_key=f"key-{number}",
        total=1210,
    )


def refused(make):
    with pytest.raises(IntegrityError), transaction.atomic():
        make()


# Series


def test_a_series_is_unique_by_code_and_year():
    series("FACT", 2026)
    series("FACT", 2027)
    refused(lambda: series("FACT", 2026))


def test_a_year_has_one_default_series_at_most():
    series("FACT", 2026, is_default=True)
    series("TICKET", 2027, invoice_type="F2", is_default=True)
    refused(lambda: series("OTHER", 2026, is_default=True))


def test_the_counter_never_goes_below_zero():
    refused(lambda: series(current_number=-1))


def test_a_factory_series_is_named_in_the_readers_language():
    ticket = series("TICKET", invoice_type="F2", name="POS tickets")
    own = series("SHOP", name="Online shop")
    with translation.override("es"):
        assert ticket.display_name == "Tiques del TPV"
        assert own.display_name == "Online shop"
    renamed = series("RECT", invoice_type="R1", name="Abonos")
    assert renamed.display_name == "Abonos"


# Issuer


def test_the_issuer_is_one_row():
    Issuer.objects.create(
        legal_name="Bar Pepe SL", tax_id="B12345674", address="Calle Mayor 1"
    )
    refused(
        lambda: Issuer.objects.create(
            legal_name="Other", tax_id="B00000000", address="x"
        )
    )


def test_the_issuer_is_configured_with_name_tax_id_and_address():
    issuer = Issuer(legal_name="Bar Pepe SL", tax_id="B12345674", address="")
    assert issuer.configured is False
    issuer.address = "Calle Mayor 1"
    assert issuer.configured is True
    issuer.postal_code, issuer.city, issuer.province = "28001", "Madrid", "Madrid"
    assert issuer.address_line == "Calle Mayor 1, 28001 Madrid (Madrid)"


# Invoices


def test_a_number_is_unique_in_its_series_and_a_sequence_too():
    fact = series()
    document(fact, 1)
    refused(lambda: document(fact, 2, number="FACT-2026-000001"))
    refused(lambda: document(fact, 1, number="FACT-2026-X"))


def test_the_same_number_in_another_series_code_is_another_document():
    document(series("FACT"), 1, number="A-1")
    document(series("SHOP"), 1, number="A-1")


def test_the_total_is_base_plus_tax():
    refused(lambda: document(series(), base=1000, tax=210, total_amount=1200))


def test_an_ordinary_document_is_never_negative_and_a_rectifying_one_never_positive():
    fact = series()
    refused(lambda: document(fact, base=-1000, tax=-210))
    rect = series("RECT", invoice_type="R1")
    original = document(fact, 1)
    refused(lambda: document(rect, 1, base=1000, tax=210, rectifies=original))
    document(rect, 2, base=-1000, tax=-210, rectifies=original)


def test_a_rectifying_document_names_what_it_rectifies():
    refused(lambda: document(series("RECT", invoice_type="R1"), base=-1, tax=0))


def test_a_substitute_names_its_ticket_and_a_ticket_has_one_at_most():
    ticket = document(series("TICKET", invoice_type="F2"), 1)
    fact = series()
    refused(lambda: document(fact, 1, invoice_type="F3"))
    document(fact, 1, invoice_type="F3", substitutes=ticket)
    refused(lambda: document(fact, 2, invoice_type="F3", substitutes=ticket))


def test_one_invoice_per_sale_and_one_rectification_per_void():
    sale_id = a_sale().id
    fact = series()
    rect = series("RECT", invoice_type="R1")
    original = document(fact, 1, source_type="sale", source_sale_id=sale_id)
    refused(lambda: document(fact, 2, source_type="sale", source_sale_id=sale_id))
    document(
        rect,
        1,
        base=-1000,
        tax=-210,
        rectifies=original,
        source_type="void",
        source_sale_id=sale_id,
    )
    refused(
        lambda: document(
            rect,
            2,
            base=-1,
            tax=0,
            rectifies=original,
            source_type="void",
            source_sale_id=sale_id,
        )
    )


def test_one_rectification_per_refund():
    from apps.sale.models import Refund

    refund_id = Refund.objects.create(sale=a_sale(), total=121, reason="broken").id
    original = document(series(), 1)
    rect = series("RECT", invoice_type="R1")
    document(
        rect,
        1,
        base=-100,
        tax=-21,
        rectifies=original,
        source_type="refund",
        source_refund_id=refund_id,
    )
    refused(
        lambda: document(
            rect,
            2,
            base=-100,
            tax=-21,
            rectifies=original,
            source_type="refund",
            source_refund_id=refund_id,
        )
    )


def test_kinds_of_document():
    ticket = document(series("TICKET", invoice_type="F2"), 1)
    assert (ticket.is_simplified, ticket.is_rectification) == (True, False)
    rect = document(
        series("RECT", invoice_type="R5"), 1, base=-1000, tax=-210, rectifies=ticket
    )
    assert (rect.is_simplified, rect.is_rectification) == (True, True)


def test_a_line_squares():
    invoice = document(series())
    InvoiceLine.objects.create(
        invoice=invoice,
        position=1,
        description="Coffee",
        quantity="2",
        unit_price=500,
        tax_rate="21.00",
        base_amount=1000,
        tax_amount=210,
        total_amount=1210,
    )
    refused(
        lambda: InvoiceLine.objects.create(
            invoice=invoice,
            position=2,
            description="Tea",
            quantity="1",
            unit_price=500,
            tax_rate="21.00",
            base_amount=500,
            tax_amount=105,
            total_amount=600,
        )
    )
    refused(
        lambda: InvoiceLine.objects.create(
            invoice=invoice,
            position=3,
            description="Tea",
            quantity="1",
            unit_price=-500,
            tax_rate="21.00",
            base_amount=-500,
            tax_amount=-105,
            total_amount=-605,
        )
    )


def test_the_columns_verifactu_reads_fit_its_xsd():
    # SuministroInformacion.xsd: NombreRazon ≤ 120, NumSerieFactura ≤ 60, IDOtro's ID ≤ 20,
    # DescripcionOperacion ≤ 500.
    limits = {
        (Invoice, "customer_name"): 120,
        (Invoice, "issuer_name"): 120,
        (Invoice, "number"): 60,
        (Invoice, "customer_tax_id"): 20,
        (Invoice, "issuer_tax_id"): 20,
        (Invoice, "description"): 500,
        (Issuer, "legal_name"): 120,
        (Issuer, "tax_id"): 20,
    }
    assert {
        (model.__name__, name): model._meta.get_field(name).max_length
        for model, name in limits
    } == {(model.__name__, name): limit for (model, name), limit in limits.items()}

