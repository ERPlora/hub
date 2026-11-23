"""A turn offers only the tools nearest the person's words, and the search of the rest last
(``base.assistant.find_tools``). Told nothing of that search, the model took the tools it was given for all it had:
after adding two coffees to table 4 it said «I can't remove lines from here», and asked to bump a cheesecake to 6 euros
«I don't have a tool to update a product's price», with both tools one search away. The instructions name the search
now and say nothing is impossible here before it, as the providers of on-demand tools advise."""

import pytest
from live import assistant as shared

from base import assistant
from base.models import Membership
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import owner_of_a
from base.tests.test_assistant_tool_search import SEARCH, turn, user

__all__ = ["in_business_a"]

SEARCH_FIRST = (
    "- The tools you are given are only the ones nearest the person's words: the rest of theirs you find with "
    "`base__assistant__find_tools`. Never say that something cannot be done here, nor that you have no tool for it, "
    "before you search for it; if your searches find none, say on which screen it is done."
)

#: What the person said, the tool it needed and the turn did not offer, and the task the model searches it by.
REPORTED = [
    (
        "en",
        ("Add two coffees to the table's bill.", "Table 4, in the dining room."),
        "sale.order.remove_line",
        "remove a line of an open check",
    ),
    ("en", ("Bump the QA cheesecake up to 6 euros.",), "inventory.product.update", "change a product's price"),
]


def _plain(text: str) -> str:
    return " ".join(text.split())


@HUB_DB
@pytest.mark.parametrize(("language", "said", "name", "task"), REPORTED, ids=["remove-line", "product-price"])
def test_a_tool_left_out_of_the_turn_is_one_search_away_and_the_instructions_send_the_model_there(
    make_user, language, said, name, task
):
    context = owner_of_a(make_user, language)
    messages = [message for text in said for message in (user(text), {"role": "assistant", "content": "…"})][:-1]
    plan = turn(context, *messages)
    offered = [tool["name"] for tool in plan["tools"]]
    assert shared.tool_name(name) not in offered  # the case reported: the turn did not offer it
    assert offered[-1] == shared.tool_name(SEARCH)
    assert name in [op.name for op in assistant.relevance.found(assistant.tools.catalog(context), task, language)]
    assert SEARCH_FIRST in _plain(plan["instructions"])


def test_the_instructions_no_longer_send_the_person_to_a_screen_before_the_search():
    text = _plain(assistant.prompt.instructions(language="en", currency="EUR", decimals=2, business="Bar Pepe", screens={}))
    assert SEARCH_FIRST in text
    assert "(you have no tool for it), say on which screen it is done" not in text


@pytest.mark.parametrize("role", [Membership.Role.EMPLOYEE, Membership.Role.MANAGER, Membership.Role.ACCOUNTANT])
def test_a_role_below_the_owner_is_told_it_cannot_only_after_the_search(role):
    """Their tools are offered as the owner's: only the nearest ones. What they may not do the search never finds
    (it reads only their own tools), so it is not available to them once the search finds none."""
    text = _plain(
        assistant.prompt.instructions(
            language="en", currency="EUR", decimals=2, business="Bar Pepe", screens={}, role=role
        )
    )
    assert SEARCH_FIRST in text
