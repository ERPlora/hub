"""The tax ID contract: ONE reading of a recipient's tax ID, shared by Sales (at the till) and Invoicing.

A Spanish NIF, NIE or CIF and an EU VAT number are checked with python-stdnum and kept compact; a foreign
document of another kind (passport, foreign tax ID, residence certificate…) is taken as written, but only
with its kind (the AEAT's IDType 02–07): VeriFactu declares a foreign recipient as ``IDOtro``, and an
``IDOtro`` without ``IDType`` is refused by the tax agency.
"""

import pytest

from apps.customer.tax_ids import (
    HOME_COUNTRY,
    ID_TYPES,
    IdTypeRequired,
    InvalidCountry,
    InvalidTaxId,
    normalize_country,
    normalize_tax_id,
)


def test_spain_is_the_home_country_and_the_kinds_are_the_aeats():
    assert HOME_COUNTRY == "ES"
    assert ID_TYPES == ("02", "03", "04", "05", "06", "07")


def test_a_spanish_nif_nie_or_cif_is_checked_and_kept_compact():
    assert normalize_tax_id("12345678-z") == "12345678Z"
    assert normalize_tax_id(" X1234567L ", country="ES") == "X1234567L"
    assert normalize_tax_id("B-12345674", country="") == "B12345674"


def test_a_spanish_tax_id_that_does_not_check_is_refused():
    for wrong in ("12345678A", "B12345675", "HELLO"):
        with pytest.raises(InvalidTaxId):
            normalize_tax_id(wrong)


def test_an_eu_vat_number_is_checked_with_its_country_prefix():
    assert (
        normalize_tax_id("403 032 650 45", country="FR", id_type="02")
        == "FR40303265045"
    )
    assert (
        normalize_tax_id("FR40303265045", country="FR", id_type="02") == "FR40303265045"
    )
    assert normalize_tax_id("094259216", country="GR", id_type="02") == "EL094259216"
    with pytest.raises(InvalidTaxId):
        normalize_tax_id("FR40303265046", country="FR", id_type="02")


def test_a_foreign_document_of_another_kind_is_taken_as_written():
    assert normalize_tax_id(" P1234567 ", country="US", id_type="03") == "P1234567"
    assert normalize_tax_id("12-3456789", country="US", id_type="04") == "12-3456789"


def test_a_foreign_tax_id_without_its_kind_is_refused():
    with pytest.raises(IdTypeRequired):
        normalize_tax_id("P1234567", country="US")
    with pytest.raises(IdTypeRequired):
        normalize_tax_id("P1234567", country="US", id_type="99")


def test_both_refusals_are_value_errors_and_nothing_stays_nothing():
    assert issubclass(InvalidTaxId, ValueError) and issubclass(
        IdTypeRequired, ValueError
    )
    assert normalize_tax_id("   ", country="US") == ""


# The recipient's country: ONE reading too (the same as Invoicing's recipient schema)


def test_a_country_is_its_iso_3166_1_alpha_2_code_in_capitals():
    assert normalize_country(" es ") == "ES"
    assert normalize_country("fr") == "FR"
    assert normalize_country("GB") == "GB"


def test_no_country_stays_none():
    assert normalize_country("") == ""
    assert normalize_country("   ") == ""


@pytest.mark.parametrize("value", ["UK", "EL", "XK", "ZZ", "Spain", "ESP", "E"])
def test_what_is_no_iso_3166_1_code_is_refused(value):
    # As Invoicing's recipient schema: an alias (UK, the VAT prefix EL), a name or a three-letter code
    # is not the code a fiscal document carries.
    with pytest.raises(InvalidCountry):
        normalize_country(value)


def test_the_refusal_is_a_value_error():
    assert issubclass(InvalidCountry, ValueError)
