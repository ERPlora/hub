"""INVOICE-F21 asked to the assistant: the card of setting the issuer names its country as Invoicing › Issuer's picker
does, in the person's language («Spain», «España»), never by its ISO code («ES»). The write still keeps the code."""

import pytest
from live.assistant.tools import input_schema
from live.operations import get

from apps.invoice.models import Issuer
from apps.invoice.tests.conftest import HUB_DB, run
from apps.tax.choices import COUNTRY_CODES
from base import assistant

ISSUER = {
    "legal_name": "Bar QA Asistente SL",
    "country": "ES",
    "tax_id": "B12345674",
    "address": "Calle Mayor 10",
    "postal_code": "28013",
    "city": "Madrid",
    "province": "Madrid",
}


def card_lines(arguments: dict, language: str) -> list[str]:
    """Each datum of the card as the person reads it: «<its name>: <its value>»."""
    card = assistant.cards.card(get("invoice.issuer.update"), arguments, language)
    return [f"{field['label']}: {field['value']}" for field in card["fields"]]


@pytest.mark.parametrize(
    ("language", "lines"),
    [
        (
            "en",
            [
                "Legal name: Bar QA Asistente SL",
                "Country: Spain",
                "Tax ID: B12345674",
                "Address: Calle Mayor 10",
                "Postal code: 28013",
                "City: Madrid",
                "Province: Madrid",
            ],
        ),
        (
            "es",
            [
                "Razón social: Bar QA Asistente SL",
                "País: España",
                "NIF: B12345674",
                "Domicilio: Calle Mayor 10",
                "Código postal: 28013",
                "Ciudad: Madrid",
                "Provincia: Madrid",
            ],
        ),
    ],
)
def test_the_issuer_card_says_its_country_by_its_name_in_the_persons_language(language, lines):
    assert card_lines(ISSUER, language) == lines


@pytest.mark.parametrize(("language", "france"), [("en", "France"), ("es", "Francia")])
def test_a_business_abroad_reads_its_own_country_on_the_card(language, france):
    assert f"{'Country' if language == 'en' else 'País'}: {france}" in card_lines({**ISSUER, "country": "FR"}, language)


def test_the_assistant_may_send_every_country_the_issuer_takes():
    """The closed list the assistant is offered is the one the write accepts: none left out, none it refuses."""
    country = input_schema(get("invoice.issuer.update"))["properties"]["country"]
    assert country["enum"] == list(COUNTRY_CODES)


@HUB_DB
def test_the_write_keeps_the_country_code_the_card_named():
    run("invoice.issuer.update", {**ISSUER, "country": "ES"})
    assert Issuer.objects.get().country == "ES"
