"""hub#2288: the card of an invoice made by hand says each of its lines — what it bills, its tax, how many and its price
without VAT —, never «Lines: 2 items»: an issued invoice is never edited, so the person checks its amounts before
saying yes. A typed rate is said as a percentage, as the invoice prints it; a tax category, by its name and its rate
(INVOICE-F03).
"""

import dataclasses

import pytest
from live.assistant import NAMED
from live.operations import get

from apps.invoice.tests.conftest import HUB_DB, ctx_for
from base import assistant

PARTY = {"customer_name": "Bodas Sur QA SL", "customer_tax_id": "B24680134", "customer_address": "Calle Alcalá 200"}
MENUS = {"description": "Menús de cumpleaños privado", "quantity": "30", "unit_price": 2273, "tax_rate": "10"}
ROOM = {"description": "Alquiler del salón", "quantity": "1", "unit_price": 12397, "tax_rate": "21"}
#: How each language writes a percentage (CLDR): Spanish with a no-break space before the sign.
PERCENT = {"en": "{}%", "es": "{} %"}


def lines_of(lines: list[dict], language: str = "en") -> dict:
    ctx = dataclasses.replace(ctx_for(), language=language)
    card = assistant.cards.card(get("invoice.invoice.create"), {**PARTY, "lines": lines}, language, ctx)
    return next(field for field in card["fields"] if field["name"] == "lines")


def money(cents: int) -> dict:
    return {"kind": "money", "value": cents}


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_each_line_says_what_it_bills_its_rate_how_many_and_its_price(language):
    """The issue's card said «Líneas: 2 elementos»."""
    said = lines_of([MENUS, ROOM], language)
    percent = PERCENT[language]
    assert said["value"] == [
        {"description": "Menús de cumpleaños privado", "quantity": "30", "unit_price": money(2273), "tax_rate": percent.format(10)},
        {"description": "Alquiler del salón", "quantity": "1", "unit_price": money(12397), "tax_rate": percent.format(21)},
    ]
    assert said.get(NAMED) is True


@HUB_DB
def test_a_rate_with_decimals_keeps_them():
    said = lines_of([{**MENUS, "tax_rate": "5.5"}], "es")
    assert said["value"][0]["tax_rate"] == "5,5 %"


@HUB_DB
def test_a_line_with_a_tax_category_says_the_category_by_its_name_and_its_rate():
    said = lines_of([{**MENUS, "tax_rate": None, "tax_category_key": "restaurant.food"}])
    assert said["value"][0]["tax_category_key"] == "Restaurant — food · 10%"
    assert said.get(NAMED) is True


@HUB_DB
def test_a_rate_that_is_none_is_said_as_written():
    """The write refuses it; the card makes up no percentage."""
    said = lines_of([{**MENUS, "tax_rate": "diez"}])
    assert said["value"][0]["tax_rate"] == "diez"
