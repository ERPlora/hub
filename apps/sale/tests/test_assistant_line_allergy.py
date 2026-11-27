"""A guest's allergy said to the assistant for their dish is marked on the dish's line (SALE-F41), never turned down
as the customer's health data, which only the «Health and allergies» block of the card keeps (CUSTOMER-F32).

Told «La clienta de la 4 es celíaca, márcalo en su plato.» with table 4's check open, the assistant answered twice
that it could not keep health data and sent the person to the customer's card: «clienta» brings Customers' tools,
whose free texts said it had no tool for allergies at all, so it never searched for the one of the line.
"""

import pytest
from live.assistant import description
from live.operations import get

from apps.sale.tests.conftest import HUB_DB, ctx_for
from base import assistant
from base.tests.assistant_context import owner_of_a
from base.tests.test_assistant_asks import assert_offered_or_found

LINE_ALLERGY = "sale.order.set_line_allergy"
#: The owner's words in the QA of a restaurant's lunch service, said twice in new conversations, with no dish named.
REPORTED = "La clienta de la 4 es celíaca, márcalo en su plato."
#: What the model searches for when other words bring no tool of the line, as the customer's texts tell it to.
SEARCHES = [
    ("es", "mark an allergy on a dish"),
    ("es", "mark a customer's allergy on their dish"),
    ("es", "marcar la alergia de un cliente en su plato"),
    ("es", "mark a celiac guest's dish"),
    ("en", "mark an allergy on a dish"),
]


def turn_texts(ctx, said: str) -> list[str]:
    """Every text of the tools a turn sends the model for ``said``: each description and each datum's."""
    turn = get("base.assistant.turn")
    plan = turn(ctx, turn.input(messages=[{"role": "user", "content": said}])).model_dump(mode="json")
    texts = []
    for tool in plan["tools"]:
        texts.append(tool["description"])
        texts += [datum.get("description", "") for datum in tool["parameters"].get("properties", {}).values()]
    return [" ".join(text.split()) for text in texts]


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize("language", ["es", "en"])
def test_the_reported_allergy_is_offered_the_tool_of_the_line_with_no_search(language):
    tools = assistant.tools.catalog(ctx_for("hub_owner", language=language))
    assert_offered_or_found(tools, LINE_ALLERGY, REPORTED, None, language)


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
@pytest.mark.parametrize(("language", "search"), SEARCHES)
def test_the_search_for_an_allergy_on_a_dish_finds_the_tool_of_the_line(language, search):
    tools = assistant.tools.catalog(ctx_for("hub_owner", language=language))
    assert LINE_ALLERGY in [op.name for op in assistant.relevance.found(tools, search, language)]


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_no_text_of_the_reported_turn_says_an_allergy_on_a_dish_has_no_tool(make_user):
    texts = turn_texts(owner_of_a(make_user, "es"), REPORTED)
    to_the_card = [text for text in texts if "Never for allergies, sensitivity tests or other health data" in text]

    assert to_the_card  # positive control: «clienta» brings Customers' tools, which send health data to the card
    for text in to_the_card:
        assert "You have no tool for them" not in text
        assert "An allergy to mark on a dish someone will eat is not kept on the card" in text
        assert "it goes on that dish's line, with a tool you find by searching for it." in text


def test_the_tool_of_the_line_says_it_is_no_health_data_and_asks_for_the_dish():
    said = " ".join(description(get(LINE_ALLERGY)).split())
    assert "It is not the health data of the customer's card and needs no permission of theirs." in said
    assert "If the person does not say which dish, ask which one." in said
    assert "(a celiac: gluten)" in said
