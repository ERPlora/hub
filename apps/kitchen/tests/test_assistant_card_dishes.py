"""hub#2288: the card of a ticket made by hand says its dishes — each by the product of the catalogue, the name the
person said or what to cook, then its note and how many —, never «2 items», and says them right after where it goes,
because a normal card's line shows only its first three data (KITCHEN-F23)."""

import dataclasses

import pytest
from live.assistant import NAMED
from live.operations import get

from apps.kitchen.tests.conftest import HUB_DB, ctx_for
from base import assistant

CREATE = "kitchen.ticket.create"


def drawn(arguments: dict, language: str = "en") -> list[dict]:
    ctx = dataclasses.replace(ctx_for(), language=language)
    return assistant.cards.card(get(CREATE), arguments, language, ctx)["fields"]


def dishes(arguments: dict, language: str = "en") -> dict:
    return next(field for field in drawn(arguments, language) if field["name"] == "items")


@HUB_DB
@pytest.mark.parametrize("language", ["en", "es"])
def test_the_dishes_are_said_by_what_the_person_said_and_how_many(language):
    """The issue's card said «Create in Kitchen: Staff · Staff coffees, not billed · 2 items»."""
    items = [{"product": "Espresso", "quantity": "2"}, {"name": "White coffee", "quantity": "1", "notes": "oat milk"}]
    said = dishes({"label": "Staff", "notes": "Staff coffees, not billed", "items": items}, language)
    assert (said["value"], said.get(NAMED)) == (items, True)


@HUB_DB
def test_a_dish_of_the_catalogue_is_said_by_its_product(product):
    """By its id, the product's name; beside it, the name the model also wrote is left out, as the write ignores it."""
    burger = product("Burger")
    said = dishes({"items": [{"product_id": str(burger.id), "product": "burguer", "quantity": "3"}]})
    assert (said["value"], said.get(NAMED)) == ([{"product_id": "Burger", "quantity": "3"}], True)


@HUB_DB
def test_the_dishes_come_right_after_where_the_ticket_goes():
    """Its type and its notes come after: the cook's dishes are what the person checks."""
    arguments = {
        "order_type": "takeaway",
        "label": "Staff",
        "notes": "Staff coffees, not billed",
        "items": [{"product": "Espresso", "quantity": "2"}],
    }
    assert [field["name"] for field in drawn(arguments)] == ["label", "items", "order_type", "notes"]
