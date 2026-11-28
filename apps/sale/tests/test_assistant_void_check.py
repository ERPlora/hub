"""Deleting a table's open check through the Hub's assistant, as the till's «Delete check» button does.

The screen calls voiding a check «deleting» it («Delete check», «Delete an open check with something on it»), so a
person asks the assistant to delete it too. Their words have to bring the void (``sale.order.void``) among the tools a
turn offers, and the model's own search for the task has to find it, never only closing the table or removing lines
one by one. Whoever may not void a check with something on it is sent by the void's description to the manager's door
(``sale.order.void_ordered``), which a search in those words finds.
"""

import pytest
from live import assistant as shared
from live.operations import get

from apps.sale.tests.conftest import HUB_DB, ctx_for
from base import assistant
from base.tests.test_assistant_asks import offered_to

VOID = "sale.order.void"
VOID_ORDERED = "sale.order.void_ordered"

#: What the employee and the manager said, word for word, when the assistant closed the table or removed lines instead.
SAID = [
    pytest.param("hub_employee", "La cuenta de la mesa 3 la abrimos por error, elimínala.", id="employee"),
    pytest.param("hub_manager", "Elimina la cuenta de la mesa 2, que se han ido sin tomar nada.", id="manager"),
]

#: What the model searched for then, in its own words, and did not find the void with.
SEARCHED = [
    pytest.param("hub_employee", "eliminar cancelar cuenta abierta de una mesa", id="employee"),
    pytest.param("hub_manager", "eliminar cuenta abierta de venta o mesa", id="manager"),
]


@HUB_DB
@pytest.mark.parametrize(("role", "phrase"), SAID)
def test_asking_to_delete_a_tables_check_offers_its_void(role, phrase):
    tools = assistant.tools.catalog(ctx_for(role, language="es"))
    assert VOID in tools  # positive control: whoever builds checks holds it
    assert VOID in offered_to(tools, phrase, "es")


@HUB_DB
@pytest.mark.parametrize(("role", "task"), SEARCHED)
def test_searching_to_delete_a_check_finds_its_void(role, task):
    tools = assistant.tools.catalog(ctx_for(role, language="es"))
    assert VOID in [op.name for op in assistant.relevance.found(tools, task, "es")]


def test_the_void_sends_whoever_may_not_void_to_the_managers_door_and_says_how_to_find_the_check():
    description = shared.description(get(VOID))
    for named in (VOID_ORDERED, "sale.order.list"):
        assert named in description


@HUB_DB
@pytest.mark.parametrize(
    ("language", "task"),
    [("en", "void a check with something ordered on it"), ("es", "anular una cuenta con algo pedido")],
)
def test_an_employee_searching_for_the_managers_door_finds_it(language, task):
    tools = assistant.tools.catalog(ctx_for("hub_employee", language=language))
    assert VOID_ORDERED in tools  # positive control: a manager approves it for them, as on the till
    assert VOID_ORDERED in [op.name for op in assistant.relevance.found(tools, task, language)]
