"""The issuer of a document as it is read and printed: its tax ID as kept, the one VeriFactu declares and the QR
carries, and beside it the one the paper prints, its EU VAT number while the issuer is registered for intra-EU
operations (ROI). The Hub knows that only of ERPlora, whose tax identity is the platform issuer's."""

from types import SimpleNamespace

from apps.invoice.document_issuer import document_issuer, issuer_vat_number

#: ERPlora's tax ID in a test (never the real one).
ERPLORA = "B12345674"


def test_erplora_prints_its_eu_vat_number_with_its_countrys_prefix(settings):
    settings.PLATFORM_ISSUER_TAX_ID = ERPLORA

    assert issuer_vat_number(ERPLORA, "ES") == "ESB12345674"


def test_an_issuer_without_a_country_is_a_spanish_one(settings):
    settings.PLATFORM_ISSUER_TAX_ID = ERPLORA

    assert issuer_vat_number(ERPLORA, "") == "ESB12345674"


def test_any_other_issuer_prints_its_tax_id_as_kept(settings):
    settings.PLATFORM_ISSUER_TAX_ID = "B27593136"

    assert issuer_vat_number(ERPLORA, "ES") == ERPLORA


def test_the_issuer_of_a_document_keeps_its_bare_tax_id_beside_the_one_it_prints(settings):
    settings.PLATFORM_ISSUER_TAX_ID = ERPLORA
    invoice = SimpleNamespace(
        issuer_name="ERPLORA CLOUD SL",
        issuer_tax_id=ERPLORA,
        issuer_address="Avda. de Lisboa, 17, 2º C",
        issuer_country="ES",
    )

    assert document_issuer(invoice) == {
        "issuer_name": "ERPLORA CLOUD SL",
        "issuer_tax_id": ERPLORA,
        "issuer_vat_number": "ESB12345674",
        "issuer_address": "Avda. de Lisboa, 17, 2º C",
        "issuer_country": "ES",
    }
