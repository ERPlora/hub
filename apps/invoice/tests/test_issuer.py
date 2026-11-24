"""The issuer, the business's tax identity: what it needs, how its tax ID is checked and the SaaS's photo of it."""

import pytest
from pydantic import ValidationError

from apps.invoice.schemas.issuer import IssuerIn, IssuerSyncIn
from apps.invoice.tests.conftest import ISSUER, fields


def test_the_issuer_needs_name_tax_id_and_address_and_a_valid_spanish_nif():
    ok = IssuerIn.model_validate(
        {"legal_name": "Bar Pepe SL", "tax_id": "b12345674", "address": "Calle Mayor 1"}
    )
    assert (ok.tax_id, ok.country) == ("B12345674", "ES")
    with pytest.raises(ValidationError) as refused:
        IssuerIn.model_validate(
            {"legal_name": " ", "tax_id": "B12345678", "address": ""}
        )
    assert fields(refused.value) == {"legal_name", "tax_id", "address"}


def test_a_foreign_issuer_keeps_its_tax_id_as_written():
    ok = IssuerIn.model_validate(
        {
            "legal_name": "Café SARL",
            "tax_id": "123 456",
            "address": "Rue 1",
            "country": "fr",
        }
    )
    assert (ok.tax_id, ok.country) == ("123 456", "FR")


@pytest.mark.parametrize("version", [{}, {"version": -1}])
def test_the_photo_of_the_issuer_says_its_version(version):
    assert IssuerSyncIn.model_validate({**ISSUER, "version": 0}).version == 0
    with pytest.raises(ValidationError) as refused:
        IssuerSyncIn.model_validate({**ISSUER, **version})
    assert fields(refused.value) == {"version"}
