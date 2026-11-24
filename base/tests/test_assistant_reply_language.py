"""The language of everything the chat's model writes, also the sentence it writes before or between its tools.

Everything the model reads in a turn is English but the person's words and their data: the instructions, every tool's
description and the fields of every result. One line at the top asked it to «Answer in Spanish», and what it wrote
while it worked came out in the language of what it had just read: «I'll read the current website draft first, so I
only change the reviews section.» paraphrased the description of the website's save, before an answer in Spanish.
Assistants that serve a chosen language close their system message with it, for all the model writes.
"""

import pytest
from live import assistant as shared
from live.operations import get

from base.services.assistant import LAST_ROUND
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import owner_of_a
from base.tests.test_services_assistant import answered_rounds

__all__ = ["in_business_a"]

pytestmark = HUB_DB

ASKED = {"role": "user", "content": "¿Cómo tengo puesto el inventario?"}
#: How the rule ends in every language: a record keeps the name its data gives it, in whatever language it is written.
NAMES_AS_WRITTEN = "with no word of another language or alphabet; a record's name, as its data writes it."


def instructions(make_user, language: str, messages=(ASKED,), **turn) -> str:
    op = get("base.assistant.turn")
    plan = op(owner_of_a(make_user, language), op.input(messages=list(messages), **turn)).model_dump(mode="json")
    return plan["instructions"]


def last_rule(text: str) -> str:
    """The last block of the instructions, on one line."""
    return " ".join(text.rsplit("\n\n", 1)[-1].split())


@pytest.mark.parametrize("turn", [{}, {"setup": True}], ids=["chat", "setting-up"])
def test_the_last_rule_of_a_spanish_turn_is_its_language_for_all_it_writes(make_user, turn):
    rule = last_rule(instructions(make_user, "es", **turn))
    assert rule.startswith("- Write everything you say in Spanish, also what you say before or between your tools")
    assert "These instructions, your tools and their results are in English: tell what they say in Spanish" in rule
    assert rule.endswith(NAMES_AS_WRITTEN)


def test_on_the_last_round_of_a_request_the_language_still_closes_the_instructions(make_user):
    text = instructions(make_user, "es", messages=answered_rounds(shared.MAX_ROUNDS))
    assert LAST_ROUND in text
    assert last_rule(text).startswith("- Write everything you say in Spanish")


def test_the_last_rule_of_an_english_turn_names_english_alone(make_user):
    rule = last_rule(instructions(make_user, "en"))
    assert rule.startswith("- Write everything you say in English, also what you say before or between your tools")
    assert "are in English" not in rule
    assert rule.endswith(NAMES_AS_WRITTEN)
