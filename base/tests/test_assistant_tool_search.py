"""The search the assistant has in every turn (``base.assistant.find_tools``): a turn offers only the fifteen tools
that best match the person's words, so when none of them does what was asked, the model searches the person's whole
catalogue for the task and the next round of the same request offers what it found.

Before it, a phrase that shared no word with the tool it needed left that tool out of the turn, and the model answered
that it could not do it («No puedo listar los productos de la categoría Bebidas desde aquí»).
"""

import pytest
from live import assistant as shared
from live.operations import get

from base import assistant
from base.tenancy.tests.business import HUB_DB, in_business_a
from base.tests.assistant_context import EMPLOYEE, MANAGER, ctx, owner_of_a
from base.tests.test_services_assistant import asked, call

__all__ = ["in_business_a"]

pytestmark = HUB_DB  # the catalogue is of the apps on in the business (base.activation)

SEARCH = "base.assistant.find_tools"


def searched(context, query: str) -> list[dict]:
    op = get(SEARCH)
    return op(context, op.input(query=query)).model_dump(mode="json")["tools"]


def names(tools: list[dict]) -> list[str]:
    return [tool["name"] for tool in tools]


def search_call(query: str) -> dict:
    return call(SEARCH, {"query": query}, "s1")


def answer(call: dict, content: str = "{}") -> dict:
    return {"role": "tool", "tool_call_id": call["call_id"], "content": content}


def user(text: str) -> dict:
    return {"role": "user", "content": text}


def turn(context, *messages: dict, pending: tuple[dict, ...] = ()) -> dict:
    op = get("base.assistant.turn")
    return op(context, op.input(messages=list(messages), pending=list(pending))).model_dump(mode="json")


@pytest.mark.parametrize("permissions", [EMPLOYEE, MANAGER, {"*"}])
def test_every_turn_offers_the_search_to_everybody(permissions):
    plan = turn(ctx(permissions), user("zzz"))
    assert names(plan["tools"])[-1] == shared.tool_name(SEARCH)


def test_the_search_is_the_assistants_own_and_takes_no_place_from_the_persons_tools(make_user):
    """It is no tool of the person's (``base.assistant.*``): it never ranks, so every tool a turn offers keeps the place
    its words give it, and the search takes the last one."""
    tools = assistant.tools.catalog(owner_of_a(make_user, "es"))
    assert SEARCH not in tools
    ranking = assistant.relevance.ranking(tools)
    for said in ("Sube un 5 % las bebidas", "¿Qué vendí hoy?"):
        ranked = [op.name for op in shared.relevant(tools, [said], "es", **ranking)]
        offered = [op.name for op in assistant.relevance.relevant(tools, [said], "es")]
        assert offered == [*ranked[: assistant.relevance.PLACES], SEARCH]


def test_a_turn_offers_fifteen_tools_and_the_search_of_the_rest(make_user):
    """«¿cuántos productos tengo?» names many more tools than a turn offers (every read of the products and the stock).
    On the QA's phrases, fifteen places keep every tool a request needs; each place more only sends the model a tool
    nobody asked for, and each one less leaves out tools the requests need."""
    context = owner_of_a(make_user, "es")
    tools = assistant.tools.catalog(context)
    said = "¿cuántos productos tengo?"
    ranked = [op.name for op in shared.relevant(tools, [said], "es", **assistant.relevance.ranking(tools))]
    assert len(ranked) > 15  # positive control: the words name more tools than fit
    assert [op.name for op in assistant.relevance.relevant(tools, [said], "es")] == [*ranked[:15], SEARCH]
    assert len(turn(context, user(said))["tools"]) == 16


def test_after_a_search_the_turn_keeps_fifteen_places_with_what_it_found_first(make_user):
    """What the model searched for goes right after what is always at hand, and the person's words fill what is left of
    the fifteen places."""
    context = owner_of_a(make_user, "es")
    tools = assistant.tools.catalog(context)
    said, task = "¿cuántos productos tengo?", "crear una franja de reservas"
    found = [op.name for op in assistant.relevance.found(tools, task, "es")]
    offered = [op.name for op in assistant.relevance.relevant(tools, [said], "es", searched=[task])]
    always = list(assistant.relevance.ALWAYS)
    assert offered[: len(always) + len(found)] == [*always, *found]
    assert len(offered) == 16
    assert offered[-1] == SEARCH


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
    assert not set(found) & {shared.tool_name(name) for name in (*assistant.relevance.ALWAYS, SEARCH)}


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
    pytest.param(
        "es",
        "cambia «Sin cilantro» por «Nada de cilantro»",
        ("change a quick note", "cambiar una nota rápida"),
        "sale.quick_note.update",
        id="hub-1201",
    ),
    pytest.param(
        "en",
        'change "Well done" to "Medium"',
        ("change a text", "cambiar un texto"),
        "sale.quick_note.update",
        id="live-167",
    ),
    pytest.param(
        "es",
        "sustituye «Poco hecho» por «Al punto»",
        ("replace a text", "sustituir un texto"),
        "sale.quick_note.update",
        id="live-168",
    ),
    pytest.param(
        "es",
        "registra una entrada de 12 unidades de tarta",
        ("receive goods into stock", "recibir mercancía"),
        "inventory.stock.receive",
        id="hub-1834",
    ),
    pytest.param(
        "es",
        "quita Fichajes del menú",
        ("turn off an app", "desactivar una app"),
        "base.app.disable",
        id="hub-1837",
    ),
    pytest.param(
        "es",
        "apunta que ha llegado el pedido de harina",
        ("record received stock", "registrar la entrada de mercancía"),
        "inventory.stock.receive",
        id="hub-1848",
    ),
    pytest.param(
        "en",
        "record an entry of 20 € in the shift",
        ("add a cash movement", "apuntar un movimiento de caja"),
        "cash_register.movement.add",
        id="hub-1852",
    ),
    pytest.param(
        "es",
        "Me he quedado sin tinte: que no se pueda reservar el tinte de raíz hasta que me llegue el pedido",
        ("change a service", "cambiar un servicio"),
        "service.service.update",
        id="hub-1903",
    ),
    pytest.param(
        "es",
        "Carmen Ruiz se ha mudado y ya no viene: anula la cita que tenía el jueves y márcala como inactiva, sin "
        "borrar su ficha",
        ("change a customer's card", "cambiar la ficha de una clienta"),
        "customer.customer.update",
        id="hub-1904",
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
        plan = turn(context, user(said), asked(call), pending=(call,))
        assert [row["outcome"] for row in plan["executed"]] == ["ok"], task
        assert shared.tool_name(expected) in names(plan["tools"]), task
        assert len(plan["tools"]) <= assistant.relevance.PLACES + 1


def test_a_search_the_model_wrote_wrong_finds_nothing_and_the_turn_goes_on(make_user):
    context = owner_of_a(make_user, "es")
    call = {"call_id": "s1", "name": shared.tool_name(SEARCH), "arguments": "list the products"}
    plan = turn(context, user("Sube un 5 % las bebidas"), asked(call), pending=(call,))
    assert [row["outcome"] for row in plan["executed"]] != ["ok"]  # the model hears its search was not done
    assert names(plan["tools"]) == names(turn(context, user("Sube un 5 % las bebidas"))["tools"])


def test_a_search_of_a_request_already_done_no_longer_takes_a_place_in_the_turn(make_user):
    """A write the model asked for closes the request: what it searched for before is not what is asked now."""
    context = owner_of_a(make_user, "es")
    search = search_call("ver los productos de una categoría")
    write = call("inventory.product.update", {"name": "Agua", "price": "1.60"}, "w1")
    later = [answer(write), {"role": "assistant", "content": "Hecho."}, user("Gracias."), user("¿Qué vendí hoy?")]
    done = [user("Sube un 5 % las bebidas"), asked(search), answer(search), asked(write)]
    assert names(turn(context, *done, *later)["tools"]) == names(turn(context, *later)["tools"])


def test_the_latest_search_is_offered_first_when_the_model_searched_several_times(make_user):
    """A model that found nothing fitting searches again in other words: what it found last is never left out."""
    context = owner_of_a(make_user, "en")
    tasks = ["list the customers", "open the cash register", "list the reservations", "list the tables"]
    earlier = [call(SEARCH, {"query": task}, f"s{at}") for at, task in enumerate(tasks)]
    latest = call(SEARCH, {"query": "create a product"}, "s9")
    messages = [user("The tonic water is new"), *(m for c in earlier for m in (asked(c), answer(c))), asked(latest)]
    plan = turn(context, *messages, pending=(latest,))
    assert shared.tool_name("inventory.product.create") in names(plan["tools"])
