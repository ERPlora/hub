"""The tools a turn of the Hub's assistant offers come from the request the person still has open: what they asked
and what they answered to the assistant's questions about it, however many questions it took. A write the model asks
for closes its request; from the next message on, the tools are of what comes after it."""

import json

import pytest
from live import assistant as shared
from live.context import OperationContext
from live.operations import get

from base.models import Membership
from base.permissions import permissions_for
from base.tenancy.tests.business import HUB_DB, A, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB

CREATE = shared.tool_name("inventory.product.create")


@pytest.fixture
def owner(make_user):
    user = make_user("olga", host=A.key, role=Membership.Role.OWNER)
    return OperationContext(scope=A, actor=user, permissions=permissions_for(user, A), language="es")


def offered(ctx: OperationContext, *messages: dict) -> list[str]:
    op = get("base.assistant.turn")
    plan = op(ctx, op.input(messages=list(messages))).model_dump(mode="json")
    return [tool["name"] for tool in plan["tools"]]


def person(text: str) -> dict:
    return {"role": "user", "content": text}


def assistant(text: str) -> dict:
    return {"role": "assistant", "content": text}


def asked_for(name: str, arguments: dict) -> list[dict]:
    """The model's message that asked for the tool ``name``, and what the turn told it back."""
    call = {"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}
    return [
        {"role": "assistant", "content": "", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "c1", "content": json.dumps({"ok": True})},
    ]


def test_the_tool_of_the_request_stays_while_the_person_answers_the_assistants_questions(owner):
    tools = offered(
        owner,
        person("Añade la tarta de zanahoria a 5,50"),
        assistant("¿Qué código le pongo?"),
        person("No tiene código, ponle tú uno"),
        assistant("¿Qué IVA lleva?"),
        person("Es comida, el mismo IVA que los otros postres"),
    )

    assert CREATE in tools


def test_a_write_the_model_asked_for_closes_its_request(owner):
    request = [
        person("Añade la tarta de zanahoria a 5,50"),
        assistant("¿Qué código le pongo?"),
        person("No tiene código, ponle tú uno"),
    ]
    assert CREATE in offered(owner, *request)  # positive control: before its write, the request brings it

    tools = offered(
        owner,
        *request,
        *asked_for(CREATE, {"name": "Tarta de zanahoria", "price": 550}),
        assistant("Hecho: la tarta de zanahoria ya está en la carta."),
        person("¿Cuánto he vendido hoy?"),
        assistant("Hoy llevas 320 €."),
        person("¿Y ayer?"),
    )

    assert CREATE not in tools


@pytest.mark.parametrize("calls", ["c1", [None], [{"id": "c1", "function": None}], [{"id": "c1", "function": "x"}]])
def test_a_call_the_turn_cannot_read_closes_nothing_and_breaks_nothing(owner, calls):
    tools = offered(
        owner,
        person("Añade la tarta de zanahoria a 5,50"),
        {"role": "assistant", "content": "", "tool_calls": calls},
        person("No tiene código, ponle tú uno"),
        assistant("¿Qué IVA lleva?"),
        person("Es comida, el mismo IVA que los otros postres"),
    )

    assert CREATE in tools
