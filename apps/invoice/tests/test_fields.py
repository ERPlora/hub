"""What the schemas of the invoice app share: a recipient's tax ID and country, naming a document or a sale, the page of a
list and what fits in VeriFactu's record. Each refusal names its field before anything runs.

A Spanish tax ID is checked with python-stdnum (NIF, NIE or CIF; the EU VAT number with document type 02); every list
stops at 100; a document is named by its id or its number.
"""

import pytest
from pydantic import ValidationError

from apps.invoice.schemas.fields import InvoiceRefIn
from apps.invoice.schemas.invoices import FromSaleIn, InvoiceListIn, SubstituteIn
from apps.invoice.schemas.issuer import IssuerIn
from apps.invoice.tests.conftest import fields


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
    data = SubstituteIn.model_validate(
        {"number": "TICKET-2026-000001", **recipient(customer_tax_id=tax_id)}
    )
    assert data.customer_tax_id == kept


@pytest.mark.parametrize("tax_id", ["12345678A", "B12345678", "hello"])
def test_a_spanish_tax_id_that_does_not_check_is_refused_under_its_field(tax_id):
    with pytest.raises(ValidationError) as refused:
        SubstituteIn.model_validate(
            {"number": "TICKET-2026-000001", **recipient(customer_tax_id=tax_id)}
        )
    assert fields(refused.value) == {"customer_tax_id"}


def test_an_eu_vat_number_is_checked_with_its_country():
    ok = SubstituteIn.model_validate(
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
        SubstituteIn.model_validate(
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
    data = SubstituteIn.model_validate(
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
        SubstituteIn.model_validate(
            {"number": "T-1", **recipient(customer_country="es")}
        ).customer_country
        == ""
    )
    with pytest.raises(ValidationError) as refused:
        SubstituteIn.model_validate(
            {"number": "T-1", **recipient(customer_country="XX")}
        )
    assert fields(refused.value) == {"customer_country"}


def test_a_foreign_tax_id_needs_its_kind_of_document():
    # VeriFactu declares a foreign recipient as IDOtro, which the AEAT refuses without its IDType.
    with pytest.raises(ValidationError) as refused:
        SubstituteIn.model_validate(
            {
                "number": "T-1",
                **recipient(customer_tax_id="X99 123", customer_country="US"),
            }
        )
    assert fields(refused.value) == {"customer_id_type"}


# Naming a document


def test_a_document_is_named_by_its_id_or_its_number():
    with pytest.raises(ValidationError):
        InvoiceRefIn.model_validate({})
    assert (
        InvoiceRefIn.model_validate({"number": " FACT-2026-000001 "}).number
        == "FACT-2026-000001"
    )


def test_a_sale_is_named_by_its_id_or_its_number():
    with pytest.raises(ValidationError):
        FromSaleIn.model_validate({})
    assert (
        FromSaleIn.model_validate({"sale": "20261014-0001"}).sale
        == "20261014-0001"
    )


# Lists


def test_a_list_stops_at_a_hundred_rows():
    with pytest.raises(ValidationError) as refused:
        InvoiceListIn.model_validate({"limit": 101})
    assert fields(refused.value) == {"limit"}
    assert InvoiceListIn.model_validate({}).limit == 50


def test_names_and_tax_ids_fit_verifactus_record():
    # SuministroInformacion.xsd: NombreRazon is TextMax120Type, IDOtro's ID TextMax20Type.
    with pytest.raises(ValidationError) as refused:
        SubstituteIn.model_validate(
            {"number": "T-1", **recipient(customer_name="x" * 121)}
        )
    assert fields(refused.value) == {"customer_name"}
    with pytest.raises(ValidationError) as refused:
        SubstituteIn.model_validate(
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
        IssuerIn.model_validate(issuer)
    assert fields(refused.value) == {"legal_name"}
    assert SubstituteIn.model_validate(
        {"number": "T-1", **recipient(customer_name="x" * 120)}
    ).customer_name == "x" * 120
