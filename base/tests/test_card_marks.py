"""How the card of a write says a datum as its screen does: as the write takes it, a value that means there is no
limit, and a price per its unit of sale."""

import pytest
from live.operations import get

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a

__all__ = ["in_business_a"]


def shown(card: dict, name: str) -> dict:
    return next(field for field in card["fields"] if field["name"] == name)


# ── The data as the write takes them ──────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize("sent", [300, "300", 300.0, " 300 "], ids=["a number", "a text", "with decimals", "padded"])
def test_a_supplement_the_model_sends_as_a_text_is_said_as_money(sent):
    """A menu's supplement of 3 € reached the card as «Suplemento: 300»: the model sent the figure as a text, the write
    took it as 300 cents and the card painted what was sent. It paints what the write takes, as money."""
    card = assistant.cards.card(get("combo.option.create"), {"group": "Segundo", "price_delta": sent}, "es")
    assert shown(card, "price_delta") | {"label": ""} == {"name": "price_delta", "label": "", "kind": "money", "value": 300}


@HUB_DB
def test_what_the_write_refuses_is_shown_as_sent():
    """A figure the write would refuse (a fraction of a cent) is no amount it takes: the card never rounds it into one."""
    card = assistant.cards.card(get("combo.option.create"), {"group": "Segundo", "price_delta": "3.50"}, "es")
    assert (shown(card, "price_delta")["kind"], shown(card, "price_delta")["value"]) == ("text", "3.50")


@HUB_DB
def test_an_amount_inside_a_line_sent_as_a_text_is_money_too():
    """The same inside a list of lines: the card writes each amount as one on top."""
    lines = [{"description": "Menú de cumpleaños", "quantity": "1", "unit_price": "68182", "tax_rate": "10"}]
    card = assistant.cards.card(get("invoice.invoice.create"), {"lines": lines}, "es")
    assert shown(card, "lines")["value"][0]["unit_price"] == {"kind": "money", "value": 68182}


# ── A value that means there is no limit ─────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize(("language", "words"), [("es", "Sin límite"), ("en", "No limit")])
def test_a_maximum_of_zero_says_there_is_no_limit(language, words):
    """An optional group of extras with «Máximo de elecciones: 0» read as «none may be chosen»: its 0 means no limit, as
    its screen says it."""
    card = assistant.cards.card(get("modifier.group.create"), {"name": "Extras", "max_choices": 0}, language)
    assert shown(card, "max_choices")["value"] == words
    assert shown(card, "max_choices")["choice"] is True


@HUB_DB
def test_any_other_maximum_is_said_as_a_figure():
    card = assistant.cards.card(get("modifier.group.create"), {"name": "Extras", "min_choices": 0, "max_choices": 3}, "es")
    assert (shown(card, "min_choices")["value"], shown(card, "max_choices")["value"]) == (0, 3)


# ── A price per its unit of sale ─────────────────────────────────────────────────────────────────────────────────────


@HUB_DB
@pytest.mark.parametrize(
    ("sent", "label"),
    [
        ({"pricing_unit": "kg"}, "Precio por kg"),
        ({"unit": "kg"}, "Precio por kg"),
        ({"unit": "kg", "pricing_unit": "g", "price_quantity": "100"}, "Precio por 100 g"),
        ({"pricing_unit": "l", "price_quantity": 0.5}, "Precio por 0,5 l"),
        ({"unit": "ud", "price_quantity": "100"}, "Precio por 100 ud"),
    ],
    ids=["its pricing unit", "its unit", "per 100 g", "per half a litre", "per 100 units"],
)
def test_a_price_by_weight_says_its_unit(sent, label):
    """Prawns sold by the kilo at 45 € reached the card as «Precio: 45,00 €»: it says the unit the price is for, as the
    till writes it («45,00 € / kg»), in the person's language."""
    card = assistant.cards.card(get("inventory.product.create"), {"name": "Gambas", "price": 4500, **sent}, "es")
    assert shown(card, "price") == {"name": "price", "label": label, "kind": "money", "value": 4500, "titled": True}


@HUB_DB
def test_a_price_by_weight_says_its_unit_in_english():
    card = assistant.cards.card(get("inventory.product.create"), {"name": "Prawns", "price": 4500, "unit": "kg"}, "en")
    assert shown(card, "price")["label"] == "Price per kg"


@HUB_DB
@pytest.mark.parametrize("sent", [{}, {"unit": "ud"}, {"pricing_unit": "ud", "price_quantity": "1"}])
def test_a_price_by_the_unit_is_said_alone(sent):
    """By the unit, a price says nothing more, as the till writes «1,50 €»: the screen names it as its own."""
    card = assistant.cards.card(get("inventory.product.create"), {"name": "Café", "price": 150, **sent}, "es")
    assert "titled" not in shown(card, "price")
