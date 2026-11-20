"""The search the assistant always has at hand (``base.tool.search``): a turn offers only the forty tools that best
match the person's words, so when none of them does what was asked, the model searches the person's whole catalogue
for the task and the next round of the same request offers what it found.

Before it, a phrase that shared no word with the tool it needed left that tool out of the turn, and the model answered
that it could not do it («No puedo listar los productos de la categoría Bebidas desde aquí»).
"""

import json

import pytest
from live import assistant as shared
from live.operations import get

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import EMPLOYEE, MANAGER, ctx, owner_of_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB  # the catalogue is of the apps on in the business (base.activation)

SEARCH = "base.tool.search"


def searched(context, query: str) -> list[dict]:
    op = get(SEARCH)
    return op(context, op.input(query=query)).model_dump(mode="json")["tools"]


def names(tools: list[dict]) -> list[str]:
    return [tool["name"] for tool in tools]


def search_call(query: str, call_id: str = "s1") -> dict:
    return {"call_id": call_id, "name": shared.tool_name(SEARCH), "arguments": json.dumps({"query": query})}


def write_call(name: str, arguments: dict, call_id: str) -> dict:
    return {"call_id": call_id, "name": shared.tool_name(name), "arguments": json.dumps(arguments)}


def asked_for(*calls: dict) -> dict:
    """The model's message that asked for ``calls``, as the browser keeps it."""
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": c["call_id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in calls
        ],
    }


def answer(call: dict, content: str = "{}") -> dict:
    return {"role": "tool", "tool_call_id": call["call_id"], "content": content}


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def turn(context, *messages: dict, pending: tuple[dict, ...] = ()) -> dict:
    op = get("base.assistant.turn")
    return op(context, op.input(messages=list(messages), pending=list(pending))).model_dump(mode="json")


@pytest.mark.parametrize("permissions", [EMPLOYEE, MANAGER, {"*"}])
def test_the_tool_search_is_always_at_hand_for_everybody(permissions):
    assert SEARCH in assistant.relevance.ALWAYS
    tools = assistant.tools.catalog(ctx(permissions))
    assert SEARCH in tools
    assert SEARCH in [op.name for op in assistant.relevance.relevant(tools, ["zzz"], "es")]


def test_a_search_finds_the_tools_of_the_task_described_with_what_each_does(make_user):
    found = searched(owner_of_a(make_user, "en"), "list the products of a category")
    assert "inventory__product__list" in names(found)
    assert all(tool["description"] for tool in found)
    assert len(found) <= assistant.relevance.FOUND


def test_a_search_never_finds_what_the_person_may_not_use():
    assert "demo__item__create" in names(searched(ctx(MANAGER), "create an item"))
    assert "demo__item__create" not in names(searched(ctx(EMPLOYEE), "create an item"))


def test_a_search_never_finds_what_every_turn_already_offers(make_user):
    found = names(searched(owner_of_a(make_user, "en"), "search the help and the documentation"))
    assert found
    assert not set(found) & {shared.tool_name(name) for name in assistant.relevance.ALWAYS}


#: What a person said that left out the tool it needed, and the task the model searches for then, as a model writes
#: it: in English and in the person's language.
LEFT_OUT = [
    pytest.param(
        "es",
        "Sube un 5 % las bebidas",
        ("list the products of a category", "ver los productos de una categoría"),
        "inventory.product.list",
        id="hub-1853",
    ),
    pytest.param(
        "en",
        "Three bottles of water got broken, and I just counted the soft drinks, there are 40 left",
        ("write off broken stock", "dar de baja el stock roto"),
        "inventory.stock.write_off",
        id="hub-1882",
    ),
    pytest.param(
        "es",
        "Pero la tónica es nueva y no la teníamos, ¿no puedes darla de alta tú? Es de las bebidas y la vendemos a "
        "2,50 €.",
        ("create a product", "crear un producto"),
        "inventory.product.create",
        id="hub-1894",
    ),
    pytest.param(
        "es",
        "El que ya no vendemos es el flan casero.",
        ("delete a product", "borrar un producto"),
        "inventory.product.delete",
        id="hub-1895",
    ),
    pytest.param(
        "es",
        "Daniel, a partir de ahora, los sábados sale a las 15:00 en vez de a las 19:00; el resto de días sigue igual.",
        ("change an employee's work schedule", "cambiar el horario de un empleado"),
        "staff.schedule.update",
        id="hub-1896",
    ),
]


@pytest.mark.parametrize(("language", "said", "tasks", "expected"), LEFT_OUT)
def test_the_tool_a_phrase_left_out_is_offered_once_the_model_searches_for_it(
    make_user, language, said, tasks, expected
):
    context = owner_of_a(make_user, language)
    assert expected in assistant.tools.catalog(context)  # the owner holds it: only the selection can leave it out
    assert shared.tool_name(SEARCH) in names(turn(context, user(said))["tools"])
    for task in tasks:
        call = search_call(task)
        plan = turn(context, user(said), asked_for(call), pending=(call,))
        assert [row["outcome"] for row in plan["executed"]] == ["ok"], task
        assert shared.tool_name(expected) in names(plan["tools"]), task
        assert len(plan["tools"]) <= shared.MAX_TOOLS


def test_a_search_the_model_wrote_wrong_finds_nothing_and_the_turn_goes_on(make_user):
    context = owner_of_a(make_user, "es")
    call = {"call_id": "s1", "name": shared.tool_name(SEARCH), "arguments": "list the products"}
    plan = turn(context, user("Sube un 5 % las bebidas"), asked_for(call), pending=(call,))
    assert [row["outcome"] for row in plan["executed"]] != ["ok"]  # the model hears its search was not done
    assert names(plan["tools"]) == names(turn(context, user("Sube un 5 % las bebidas"))["tools"])


def test_a_search_of_a_request_already_done_no_longer_takes_a_place_in_the_turn(make_user):
    """A write the model asked for closes the request: what it searched for before is not what is asked now."""
    context = owner_of_a(make_user, "es")
    search = search_call("ver los productos de una categoría")
    write = write_call("inventory.product.update", {"name": "Agua", "price": "1.60"}, "w1")
    later = [answer(write), {"role": "assistant", "content": "Hecho."}, user("Gracias."), user("¿Qué vendí hoy?")]
    done = [user("Sube un 5 % las bebidas"), asked_for(search), answer(search), asked_for(write)]
    assert names(turn(context, *done, *later)["tools"]) == names(turn(context, *later)["tools"])
