"""What the assistant reads where it could write down a customer's allergy.

Health data lives only in the «Health and allergies» block of the card, after the customer's explicit permission, which
only that screen records (CUSTOMER-F32), and no tool of the assistant reads or writes it. Asked «Lucía QA es alérgica al
gluten … Apúntaselo en su ficha», the assistant offered a note «Alergia al gluten» (hub#2278): out of that block, with no
permission, no warning for whoever serves her and not erased if she withdraws it. Every free text a person writes on a
card says that health data does not go there, where it goes, and that the person does it there; and that an allergy to
mark on a dish someone will eat is no datum of the card, so the assistant still marks that one on the dish's line.
"""

import json
import re
from pathlib import Path

import pytest
from django.apps import apps
from live.assistant import tool_name, tool_spec
from live.operations import get

from base.tests.assistant_context import owner_of_a

from .conftest import HUB_DB

#: The owner's words in the QA of the customers' journey, said twice in new conversations.
REPORTED = (
    "Lucía QA es alérgica al gluten y nos ha dicho que no le importa que lo apuntemos. Apúntaselo en su ficha, por favor."
)
#: The block of the card as its screen titles it, in the language the descriptions are written in.
FRONTEND = Path(apps.get_app_config("customer").path) / "frontend/locale"
HEADING = json.loads((FRONTEND / "en.json").read_text())["customer"]["health"]["heading"]
#: A screen of the Hub, named by its path.
SCREEN = re.compile(r"\(\s*(/[a-z_/-]+)\s*\)")
HEALTH_OPERATIONS = ("customer.health.detail", "customer.health.grant", "customer.health.update", "customer.health.withdraw")
#: Every free text of a card the assistant may fill, by the tool's description or by the datum of it that takes the text.
#: The entries of other apps say it on their text, not on the tool: there it moved the tool up for any question about a
#: card's data.
FREE_TEXTS = [
    ("customer.note.add", None),
    ("customer.customer.create", "notes"),
    ("customer.customer.update", "notes"),
    ("customer.customer.update", "field_values"),
    ("customer.activity.add", "text"),
]


def turn_tools(ctx, said: str) -> dict[str, dict]:
    """The tools a turn of the assistant sends the model for ``said``, by their tool names, as the model reads them."""
    turn = get("base.assistant.turn")
    plan = turn(ctx, turn.input(messages=[{"role": "user", "content": said}])).model_dump(mode="json")
    return {tool["name"]: tool for tool in plan["tools"]}


def read(tool: dict, datum: str | None) -> str:
    text = tool["description"] if datum is None else tool["parameters"]["properties"][datum]["description"]
    return " ".join(text.split())


def assert_sends_health_data_to_its_block(text: str) -> None:
    assert "Never for allergies, sensitivity tests or other health data" in text
    assert f"«{HEADING}» block of the customer's card" in text
    assert "with the customer's own explicit permission, which only that screen records" in text
    assert "No tool of yours writes that block: tell the person to do it there." in text
    assert "An allergy to mark on a dish someone will eat is not kept on the card" in text
    assert "You have no tool for them" not in text
    screens = SCREEN.findall(text)
    own = {item.path for item in apps.get_app_config("customer").navigation}
    assert screens
    assert set(screens) <= own


@HUB_DB  # the catalogue is of the apps on in the business (base.activation)
def test_the_reported_request_offers_a_note_that_says_an_allergy_is_not_a_note(make_user):
    tools = turn_tools(owner_of_a(make_user, "es"), REPORTED)
    assert tool_name("customer.note.add") in tools
    assert_sends_health_data_to_its_block(read(tools[tool_name("customer.note.add")], None))
    assert not {tool_name(name) for name in HEALTH_OPERATIONS} & set(tools)


@pytest.mark.parametrize(("name", "datum"), FREE_TEXTS)
def test_no_free_text_of_a_card_takes_health_data(name, datum):
    assert_sends_health_data_to_its_block(read(tool_spec(get(name)), datum))
