"""The language of everything the chat's model writes, also the sentence it writes before or between its tools.

Everything the model reads in a turn is English but the person's words and their data: the instructions, every tool's
description and the fields of every result. One line at the top asked it to «Answer in Spanish», and what it wrote
while it worked came out in the language of what it had just read: «I'll read the current website draft first, so I
only change the reviews section.» paraphrased the description of the website's save, before an answer in Spanish.
Assistants that serve a chosen language close their system message with it, for all the model writes.
"""

import pytest
from live.operations import get

from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import owner_of_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB


def last_rule(make_user, language: str, **turn) -> str:
    op = get("base.assistant.turn")
    asked = [{"role": "user", "content": "¿Cómo tengo puesto el inventario?"}]
    plan = op(owner_of_a(make_user, language), op.input(messages=asked, **turn)).model_dump(mode="json")
    return " ".join(plan["instructions"].rsplit("\n- ", 1)[-1].split())


@pytest.mark.parametrize("turn", [{}, {"setup": True}], ids=["chat", "setting-up"])
def test_the_last_rule_of_a_spanish_turn_is_its_language_for_all_it_writes(make_user, turn):
    rule = last_rule(make_user, "es", **turn)
    assert rule.startswith("Write everything you say in Spanish, also what you say before or between your tools")
    assert "are in English" in rule
    assert "no word of another language or alphabet" in rule


def test_the_last_rule_of_an_english_turn_names_english_alone(make_user):
    rule = last_rule(make_user, "en")
    assert rule.startswith("Write everything you say in English, also what you say before or between your tools")
    assert "are in English" not in rule
