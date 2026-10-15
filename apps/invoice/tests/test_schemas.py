"""Inputs of the invoice app's operations: what a request may say, refused per field before anything runs.

A Spanish tax ID is checked with python-stdnum (NIF, NIE or CIF; the EU VAT number with document type
02); a series code is written in capitals; a number format needs its sequence; every list stops at 100;
a document is named by its id or its number.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from apps.invoice import schemas


def fields(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in item["loc"]) for item in error.errors()}


def recipient(**more):
    return {
        "customer_name": "Ana López",
        "customer_tax_id": "12345678Z",
        "customer_address": "Calle Mayor 1",
        **more,
    }


# The recipient's tax ID


@pytest.mark.parametrize(
    ("tax_id", "kept"),
    [
        ("12345678Z", "12345678Z"),
        ("x1234567l", "X1234567L"),
        ("B12345674", "B12345674"),
        ("b-12345674", "B12345674"),
        ("ESB12345674", "B12345674"),
    ],
)
def test_a_spanish_nif_nie_or_cif_is_accepted_and_written_compact(tax_id, kept):
    data = schemas.SubstituteIn.model_validate(
        {"number": "TICKET-2026-000001", **recipient(customer_tax_id=tax_id)}
    )
    assert data.customer_tax_id == kept


@pytest.mark.parametrize("tax_id", ["12345678A", "B12345678", "hello"])
def test_a_spanish_tax_id_that_does_not_check_is_refused_under_its_field(tax_id):
    with pytest.raises(ValidationError) as refused:
        schemas.SubstituteIn.model_validate(
            {"number": "TICKET-2026-000001", **recipient(customer_tax_id=tax_id)}
        )
    assert fields(refused.value) == {"customer_tax_id"}


def test_an_eu_vat_number_is_checked_with_its_country():
    ok = schemas.SubstituteIn.model_validate(
        {
            "number": "T-1",
            **recipient(
                customer_tax_id="40303265045",
                customer_country="FR",
                customer_id_type="02",
            ),
        }
    )
    assert ok.customer_tax_id == "FR40303265045"
    with pytest.raises(ValidationError) as refused:
        schemas.SubstituteIn.model_validate(
            {
                "number": "T-1",
                **recipient(
                    customer_tax_id="FR00000000000",
                    customer_country="FR",
                    customer_id_type="02",
                ),
            }
        )
    assert fields(refused.value) == {"customer_tax_id"}


def test_a_passport_or_a_foreign_tax_id_is_taken_as_written():
    data = schemas.SubstituteIn.model_validate(
        {
            "number": "T-1",
            **recipient(
                customer_tax_id="X99 123", customer_country="US", customer_id_type="03"
            ),
        }
    )
    assert (data.customer_tax_id, data.customer_country) == ("X99 123", "US")


def test_the_country_is_iso_and_spain_is_empty():
    assert (
        schemas.SubstituteIn.model_validate(
            {"number": "T-1", **recipient(customer_country="es")}
        ).customer_country
        == ""
    )
    with pytest.raises(ValidationError) as refused:
        schemas.SubstituteIn.model_validate(
            {"number": "T-1", **recipient(customer_country="XX")}
        )
    assert fields(refused.value) == {"customer_country"}


def test_a_foreign_tax_id_needs_its_kind_of_document():
    # VeriFactu declares a foreign recipient as IDOtro, which the AEAT refuses without its IDType.
    with pytest.raises(ValidationError) as refused:
        schemas.SubstituteIn.model_validate(
            {
                "number": "T-1",
                **recipient(customer_tax_id="X99 123", customer_country="US"),
            }
        )
    assert fields(refused.value) == {"customer_id_type"}


def test_the_charge_of_a_sale_reads_its_recipient_and_lets_the_operation_decide():
    # The payload of sale.sale.completed: its other keys are ignored and its recipient is read as any other,
    # but a tax ID that does not check is kept with its refusal: a ticket goes without it, an invoice is
    # refused under that field (the operation knows which one the sale is).
    sale = {"sale_id": "01999999-0000-7000-8000-000000000000", "items": [{"x": 1}]}
    data = schemas.FromSaleIn.model_validate(
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
    wrong = schemas.FromSaleIn.model_validate({**sale, "customer_tax_id": "nonsense"})
    assert wrong.tax_id_refusal[0] == "customer_tax_id"
    foreign = schemas.FromSaleIn.model_validate(
        {**sale, "customer_tax_id": "P1234567", "customer_country": "US"}
    )
    assert foreign.tax_id_refusal[0] == "customer_id_type"
    with pytest.raises(ValidationError) as refused:
        schemas.FromSaleIn.model_validate({**sale, "customer_country": "XX"})
    assert fields(refused.value) == {"customer_country"}


# Naming a document


def test_a_document_is_named_by_its_id_or_its_number():
    with pytest.raises(ValidationError):
        schemas.InvoiceRefIn.model_validate({})
    assert (
        schemas.InvoiceRefIn.model_validate({"number": " FACT-2026-000001 "}).number
        == "FACT-2026-000001"
    )


def test_a_sale_is_named_by_its_id_or_its_number():
    with pytest.raises(ValidationError):
        schemas.FromSaleIn.model_validate({})
    assert (
        schemas.FromSaleIn.model_validate({"sale": "20261014-0001"}).sale
        == "20261014-0001"
    )


# A manual invoice


def test_a_manual_line_needs_a_rate_or_a_tax_category():
    line = {"description": "Consulting", "quantity": "1", "unit_price": 10000}
    with pytest.raises(ValidationError) as refused:
        schemas.InvoiceCreateIn.model_validate({"lines": [line]})
    assert fields(refused.value) == {"lines.0.tax_rate"}
    with_rate = schemas.InvoiceCreateIn.model_validate(
        {"lines": [{**line, "tax_rate": "21"}]}
    )
    assert with_rate.lines[0].tax_rate == Decimal("21")
    schemas.InvoiceCreateIn.model_validate(
        {"lines": [{**line, "tax_category_key": "service.generic"}]}
    )


def test_a_manual_invoice_has_one_to_a_hundred_lines_of_a_positive_quantity():
    line = {"description": "x", "quantity": "1", "unit_price": 100, "tax_rate": "21"}
    with pytest.raises(ValidationError):
        schemas.InvoiceCreateIn.model_validate({"lines": []})
    with pytest.raises(ValidationError):
        schemas.InvoiceCreateIn.model_validate({"lines": [line] * 101})
    with pytest.raises(ValidationError) as refused:
        schemas.InvoiceCreateIn.model_validate({"lines": [{**line, "quantity": "0"}]})
    assert fields(refused.value) == {"lines.0.quantity"}
    with pytest.raises(ValidationError) as refused:
        schemas.InvoiceCreateIn.model_validate({"lines": [{**line, "unit_price": -1}]})
    assert fields(refused.value) == {"lines.0.unit_price"}
    with pytest.raises(ValidationError) as refused:
        schemas.InvoiceCreateIn.model_validate(
            {"lines": [{**line, "quantity": "1.0001"}]}
        )
    assert fields(refused.value) == {"lines.0.quantity"}


def test_a_rectification_picks_r1_to_r4_and_needs_a_reason():
    ok = schemas.RectifyIn.model_validate(
        {"number": "F-1", "reason": " wrong price ", "rectification_type": "R4"}
    )
    assert (ok.reason, ok.rectification_type) == ("wrong price", "R4")
    with pytest.raises(ValidationError) as refused:
        schemas.RectifyIn.model_validate(
            {"number": "F-1", "reason": "x", "rectification_type": "R5"}
        )
    assert fields(refused.value) == {"rectification_type"}
    with pytest.raises(ValidationError) as refused:
        schemas.RectifyIn.model_validate({"number": "F-1", "reason": "  "})
    assert fields(refused.value) == {"reason"}


# Series


def test_a_series_code_is_written_in_capitals():
    data = schemas.SeriesCreateIn.model_validate(
        {"code": " shop-1 ", "invoice_type": "F1", "year": 2026}
    )
    assert data.code == "SHOP-1"
    with pytest.raises(ValidationError) as refused:
        schemas.SeriesCreateIn.model_validate(
            {"code": "shop 1", "invoice_type": "F1", "year": 2026}
        )
    assert fields(refused.value) == {"code"}


def test_a_series_format_needs_its_year_and_its_sequence():
    # Without the year, the series of the next year (born from this one) would repeat its numbers.
    for wrong in ("{prefix}-{year}", "{prefix}-{seq}"):
        with pytest.raises(ValidationError) as refused:
            schemas.SeriesCreateIn.model_validate(
                {"code": "A", "invoice_type": "F1", "year": 2026, "format": wrong}
            )
        assert fields(refused.value) == {"format"}
        with pytest.raises(ValidationError) as refused:
            schemas.SeriesUpdateIn.model_validate(
                {"series_id": "01999999-0000-7000-8000-000000000000", "format": wrong}
            )
        assert fields(refused.value) == {"format"}
    data = schemas.SeriesCreateIn.model_validate(
        {"code": "A", "invoice_type": "F1", "year": 2026, "format": " "}
    )
    assert data.format == ""


def test_the_next_number_starts_at_one_at_least():
    with pytest.raises(ValidationError) as refused:
        schemas.SeriesUpdateIn.model_validate(
            {"series_id": "01999999-0000-7000-8000-000000000000", "next_number": 0}
        )
    assert fields(refused.value) == {"next_number"}


# Lists


def test_a_list_stops_at_a_hundred_rows():
    with pytest.raises(ValidationError) as refused:
        schemas.InvoiceListIn.model_validate({"limit": 101})
    assert fields(refused.value) == {"limit"}
    assert schemas.InvoiceListIn.model_validate({}).limit == 50


def test_the_list_sorts_by_the_last_issued_first_by_default():
    data = schemas.InvoiceListIn.model_validate({})
    assert (data.sort, data.dir) == ("issued_at", "desc")


# The issuer


def test_the_issuer_needs_name_tax_id_and_address_and_a_valid_spanish_nif():
    ok = schemas.IssuerIn.model_validate(
        {"legal_name": "Bar Pepe SL", "tax_id": "b12345674", "address": "Calle Mayor 1"}
    )
    assert (ok.tax_id, ok.country) == ("B12345674", "ES")
    with pytest.raises(ValidationError) as refused:
        schemas.IssuerIn.model_validate(
            {"legal_name": " ", "tax_id": "B12345678", "address": ""}
        )
    assert fields(refused.value) == {"legal_name", "tax_id", "address"}


def test_a_foreign_issuer_keeps_its_tax_id_as_written():
    ok = schemas.IssuerIn.model_validate(
        {
            "legal_name": "Café SARL",
            "tax_id": "123 456",
            "address": "Rue 1",
            "country": "fr",
        }
    )
    assert (ok.tax_id, ok.country) == ("123 456", "FR")


def test_a_prefix_and_a_format_are_printable_ascii():
    # VeriFactu's NumSerieFactura: printable ASCII only («Fª» or «Nº» would be refused by the AEAT).
    base = {"code": "A", "invoice_type": "F1", "year": 2026}
    for field, wrong in (("prefix", "Fª"), ("format", "Nº{year}-{seq}"), ("prefix", "F\t1")):
        with pytest.raises(ValidationError) as refused:
            schemas.SeriesCreateIn.model_validate({**base, field: wrong})
        assert fields(refused.value) == {field}
    ok = schemas.SeriesCreateIn.model_validate(
        {**base, "prefix": "F/A", "format": "{prefix} {year}#{seq:04d}"}
    )
    assert (ok.prefix, ok.format) == ("F/A", "{prefix} {year}#{seq:04d}")


def test_names_and_tax_ids_fit_verifactus_record():
    # SuministroInformacion.xsd: NombreRazon is TextMax120Type, IDOtro's ID TextMax20Type.
    with pytest.raises(ValidationError) as refused:
        schemas.SubstituteIn.model_validate(
            {"number": "T-1", **recipient(customer_name="x" * 121)}
        )
    assert fields(refused.value) == {"customer_name"}
    with pytest.raises(ValidationError) as refused:
        schemas.SubstituteIn.model_validate(
            {
                "number": "T-1",
                **recipient(
                    customer_tax_id="P" * 21, customer_country="US", customer_id_type="03"
                ),
            }
        )
    assert fields(refused.value) == {"customer_tax_id"}
    issuer = {"legal_name": "x" * 121, "tax_id": "B12345674", "address": "Calle 1"}
    with pytest.raises(ValidationError) as refused:
        schemas.IssuerIn.model_validate(issuer)
    assert fields(refused.value) == {"legal_name"}
    assert schemas.SubstituteIn.model_validate(
        {"number": "T-1", **recipient(customer_name="x" * 120)}
    ).customer_name == "x" * 120

