"""Inputs of the invoices: the charge of a sale, a manual invoice and the list, refused per field before anything runs."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.invoice.schemas.invoices import FromSaleIn, InvoiceCreateIn, InvoiceListIn
from apps.invoice.tests.conftest import fields


def test_the_charge_of_a_sale_reads_its_recipient_and_lets_the_operation_decide():
    # The payload of sale.sale.completed: its other keys are ignored and its recipient is read as any other,
    # but a tax ID that does not check is kept with its refusal: a ticket goes without it, an invoice is
    # refused under that field (the operation knows which one the sale is).
    sale = {"sale_id": "01999999-0000-7000-8000-000000000000", "items": [{"x": 1}]}
    data = FromSaleIn.model_validate(
        {
            **sale,
            "customer_tax_id": "b-12345674",
            "customer_country": "ES",
            "customer_id_type": None,
            "customer_address": None,
        }
    )
    assert (data.customer_tax_id, data.customer_country, data.customer_id_type) == (
        "B12345674",
        "",
        "",
    )
    assert data.tax_id_refusal is None
    wrong = FromSaleIn.model_validate({**sale, "customer_tax_id": "nonsense"})
    assert wrong.tax_id_refusal[0] == "customer_tax_id"
    foreign = FromSaleIn.model_validate(
        {**sale, "customer_tax_id": "P1234567", "customer_country": "US"}
    )
    assert foreign.tax_id_refusal[0] == "customer_id_type"
    with pytest.raises(ValidationError) as refused:
        FromSaleIn.model_validate({**sale, "customer_country": "XX"})
    assert fields(refused.value) == {"customer_country"}


# A manual invoice


def test_a_manual_line_needs_a_rate_or_a_tax_category():
    line = {"description": "Consulting", "quantity": "1", "unit_price": 10000}
    with pytest.raises(ValidationError) as refused:
        InvoiceCreateIn.model_validate({"lines": [line]})
    assert fields(refused.value) == {"lines.0.tax_rate"}
    with_rate = InvoiceCreateIn.model_validate(
        {"lines": [{**line, "tax_rate": "21"}]}
    )
    assert with_rate.lines[0].tax_rate == Decimal("21")
    InvoiceCreateIn.model_validate(
        {"lines": [{**line, "tax_category_key": "service.generic"}]}
    )


def test_a_manual_invoice_has_one_to_a_hundred_lines_of_a_positive_quantity():
    line = {"description": "x", "quantity": "1", "unit_price": 100, "tax_rate": "21"}
    with pytest.raises(ValidationError):
        InvoiceCreateIn.model_validate({"lines": []})
    with pytest.raises(ValidationError):
        InvoiceCreateIn.model_validate({"lines": [line] * 101})
    with pytest.raises(ValidationError) as refused:
        InvoiceCreateIn.model_validate({"lines": [{**line, "quantity": "0"}]})
    assert fields(refused.value) == {"lines.0.quantity"}
    with pytest.raises(ValidationError) as refused:
        InvoiceCreateIn.model_validate({"lines": [{**line, "unit_price": -1}]})
    assert fields(refused.value) == {"lines.0.unit_price"}
    with pytest.raises(ValidationError) as refused:
        InvoiceCreateIn.model_validate(
            {"lines": [{**line, "quantity": "1.0001"}]}
        )
    assert fields(refused.value) == {"lines.0.quantity"}


# Lists


def test_the_list_sorts_by_the_last_issued_first_by_default():
    data = InvoiceListIn.model_validate({})
    assert (data.sort, data.dir) == ("issued_at", "desc")
