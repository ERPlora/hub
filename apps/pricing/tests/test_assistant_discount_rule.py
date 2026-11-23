"""The discount of a product or a category, asked of the assistant, is a discount rule of Price lists (PRICING-F11).

With a rule taking 20 % off the coffees, the owner asked «El descuento de los cafés que sea solo del 10 %, que con el
20 % no nos sale a cuenta.» The turn offered no tool of the rules: «descuento» named only the discounts of an open check
of Sales, and the model put 10 % off the coffee line of table 4. Searching its tools in its own words («cambiar el
descuento de una categoría») found no rule either. Price lists says that «el descuento de los cafés» is a rule, as «la
regla de descuento de los cafés» is, and its rules say they are the discount a product or a category gets by itself.
"""

import pytest
from django.apps import apps
from live import assistant as shared
from live.assistant import description
from live.operations import get

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import WITH_ROOM, assert_its_words_name, assert_offered_with_room, offered_to

from .conftest import HUB_DB

#: The owner's words in the QA of the restaurant.
REPORTED = "El descuento de los cafés que sea solo del 10 %, que con el 20 % no nos sale a cuenta."
#: The same request in other words: none is an ask of a tool.
OWN_WORDS = [
    ("es", "baja el descuento de los cafés al 10 %"),
    ("es", "cambia el descuento de las bebidas al 15 %"),
    ("en", "the discount on coffees should be 10 % only"),
]
#: What the model searched its tools for, and what a person would.
SEARCHES = ["cambiar el descuento de una categoría", "bajar el descuento de los cafés"]
#: A discount said of a check, or by how much it takes off: no rule.
OF_A_CHECK = [
    "hazle un 10 % de descuento a la cuenta",
    "pon un descuento del 10 % en la mesa 4",
    "pon un descuento de 5 € en la cuenta",
    "give table 4 a 10% discount",
    "a 20 % discount on the wine",
]


def test_price_lists_reads_the_discount_of_something_as_a_rule():
    """Price lists says it itself: the platform's words do not, and live alone does not either (positive control)."""
    rule = shared.stem("rule")
    said = [
        "el descuento de los cafés",
        "los descuentos de las bebidas",
        "el descuento en los vinos",
        "los descuentos en bebidas",
        "the discount on coffees",
        "the discounts on wines",
    ]
    assert_its_words_name("pricing", [(phrase, rule) for phrase in said])


def test_a_discount_said_of_a_check_or_by_how_much_names_no_rule():
    own = apps.get_app_config("pricing").assistant_synonyms
    rule = shared.stem("rule")
    assert [said for said in OF_A_CHECK if any(rule in one for one in shared.asked([said], own).concepts)] == []


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_reported_request_offers_the_rules_to_read(catalog_of):
    tools = catalog_of(Membership.Role.OWNER, "es")
    assert "pricing.rule.list" in offered_to(tools, REPORTED)


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "phrase"), OWN_WORDS)
def test_changing_the_discount_of_a_product_or_a_category_offers_its_rule(catalog_of, language, phrase):
    assert_offered_with_room(catalog_of(Membership.Role.OWNER, language), "pricing.rule.update", phrase, language)


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("query", SEARCHES)
def test_searching_for_the_discount_of_a_category_finds_its_rule(catalog_of, query):
    found = [op.name for op in assistant.relevance.found(catalog_of(Membership.Role.OWNER, "es"), query, "es")]
    assert "pricing.rule.update" in found, found


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_a_discount_on_a_line_of_a_table_still_offers_the_line_discount_first(catalog_of):
    names = offered_to(catalog_of(Membership.Role.OWNER, "es"), "ponle un 10 % de descuento al café de la mesa 4")
    line = names.index("sale.order.set_line_discount")
    assert line < WITH_ROOM
    assert "pricing.rule.update" not in names or line < names.index("pricing.rule.update")


@pytest.mark.parametrize("name", ["pricing.rule.list", "pricing.rule.update"])
def test_a_rule_is_told_as_the_discount_a_product_or_a_category_gets_by_itself(name):
    assert "the discount a product or a category gets by itself on every sale (the coffee discount)" in description(
        get(name)
    )


def test_creating_a_rule_says_a_lower_one_takes_nothing_off_what_another_covers():
    assert "a lower discount for what a rule already covers is a change of that rule" in description(
        get("pricing.rule.create")
    )
