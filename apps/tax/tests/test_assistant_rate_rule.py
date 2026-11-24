"""Putting a tax on something, asked of the assistant, reaches the rule that sets the rate of its category (TAX-F04).

With a tax category «Comida para llevar» and no rule of it, the owner asked «Ponle ya el IVA a la comida para llevar…».
The turn offered no tool of the rules, and the model proposed selling the set menu to take away. A rule is never
changed, so ``tax.rule.create`` says that creating one is what sets or changes a rate (``AI.does``): «pon», «sube» and
«set» ask for it too.
"""

import dataclasses

import pytest
from live.operations import Operation

from base import assistant
from base.models import Membership
from base.tests.test_assistant_asks import assert_offered_with_room, offered_to, place_in, place_of_no_ask

from .conftest import HUB_DB

RULE = "tax.rule.create"
#: What the model ran instead: how a menu is sold, changed.
CHOSEN_INSTEAD = "combo.combo.update"
#: The owner's words in the QA of the restaurant.
REPORTED = "Ponle ya el IVA a la comida para llevar, que mañana empezamos a vender para llevar."
#: The same request in other words, and the change of a rate there is: none is an ask of the tool.
OWN_WORDS = [
    ("es", "falta ponerle el IVA a la comida para llevar"),
    ("es", "sube el IVA de los libros al 10 %"),
    ("en", "set the VAT on takeaway food to 10 %"),
]
#: What the model searches its tools for, as ``base.assistant.find_tools`` asks: the task in a few words.
SEARCHES = [
    ("es", "poner el IVA de una categoría"),
    ("es", "poner IVA a la comida para llevar"),
    ("es", "cambiar el IVA de una categoría"),
    ("es", "asignar IVA a una categoría"),
    ("en", "set the VAT rate of a tax category"),
]


@pytest.fixture
def owners(catalog_of):
    return lambda language: catalog_of(Membership.Role.OWNER, language)


def by_its_name_alone(tools: dict[str, Operation]) -> dict[str, Operation]:
    """``tools`` as they were, with the rule's creation saying only what its name says."""
    rule = tools[RULE]
    return {**tools, RULE: dataclasses.replace(rule, ai=dataclasses.replace(rule.ai_spec(), does=()))}


def found(tools: dict[str, Operation], query: str, language: str) -> list[str]:
    return [op.name for op in assistant.relevance.found(tools, query, language)]


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_reported_request_offers_the_rule_before_the_change_of_a_menu(owners):
    tools = owners("es")
    assert place_of_no_ask(tools, RULE, REPORTED) is not None
    offered = offered_to(tools, REPORTED)
    menu = place_in(offered, CHOSEN_INSTEAD)
    assert menu is None or place_in(offered, RULE) < menu, offered
    # Its name alone does not bring it (positive control).
    assert RULE not in offered_to(by_its_name_alone(tools), REPORTED)


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "phrase"), OWN_WORDS)
def test_putting_or_changing_the_tax_of_something_offers_its_rule(owners, language, phrase):
    tools = owners(language)
    assert_offered_with_room(tools, RULE, phrase, language)
    assert RULE not in offered_to(by_its_name_alone(tools), phrase, language)


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "query"), SEARCHES)
def test_searching_how_to_put_a_tax_finds_its_rule(owners, language, query):
    tools = owners(language)
    assert RULE in found(tools, query, language), found(tools, query, language)
    assert RULE not in found(by_its_name_alone(tools), query, language)


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_taking_a_tax_off_still_offers_the_switch_of_its_rule_first(owners):
    offered = offered_to(owners("es"), "desactiva el IVA de la comida para llevar")
    asked_for = [name for name in offered if name not in assistant.relevance.ALWAYS]
    assert asked_for[0] == "tax.rule.deactivate", asked_for


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_a_menu_sold_to_take_away_still_offers_its_change(owners):
    assert_offered_with_room(owners("es"), CHOSEN_INSTEAD, "que el menú del día se venda también para llevar, cámbialo")
