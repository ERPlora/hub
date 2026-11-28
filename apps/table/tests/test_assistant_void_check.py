"""Deleting a table's open check through the Hub's assistant, as the till's «Delete check» button does it (SALE-F18,
TABLE-F20): the card names the table's check, and once confirmed the check is voided and the table is free. Whoever may
not void a check with something on it never sees that card: the assistant hears it before drawing one."""

import pytest
from live.context import OperationContext

from apps.sale.models.orders import Order
from base import assistant
from base.models import Membership
from base.permissions import access_for
from base.roles import OFF, ON
from base.tests import card_turn
from base.tests.roles import a_role, held_by

from .conftest import HUB_DB, A, add_line, ctx_for, make_table, make_zone, run

pytestmark = HUB_DB

VOID = "sale.order.void"
SAID = "Elimina la cuenta de la mesa 3, que se han ido sin tomar nada."
YES = {"call_id": "c1", "accepted": True, "typed": "CONFIRMAR"}


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


@pytest.fixture
def seated():
    """Table 3 of the dining room, seated by a waiter: its check is open and empty."""
    table = make_table("3", zone=make_zone("Comedor"))
    return table, run("table.session.open", {"table_id": str(table.id)}, ctx_for("hub_employee"))


def drawn(ctx: OperationContext, order_id) -> dict:
    """The turn in which the model asks to void the check ``order_id`` for ``ctx``'s person."""
    return card_turn.turn(ctx, card_turn.call(VOID, {"order_id": str(order_id)}), said=SAID)


def confirmed(ctx: OperationContext, order_id) -> list[str]:
    """How it went once the person typed the yes of the void's card."""
    plan = card_turn.turn(ctx, drawn(ctx, order_id)["pending"][0], said=SAID, decision=YES)
    return [row["outcome"] for row in plan["executed"]]


def state(table, session) -> tuple[str, str]:
    """The table's state on the floor and its check's in Sales."""
    return run("table.table.get", {"id": str(table.id)}).status, Order.objects.get(pk=session.order_id).status


def lines(card: dict) -> list[tuple[str, str]]:
    return [(field["label"], field["value"]) for field in card["fields"]]


@pytest.mark.parametrize("role", ["hub_manager", "hub_owner"])
def test_a_manager_confirms_the_card_and_the_tables_check_is_voided_and_the_table_free(seated, coffee, role):
    table, session = seated
    add_line(session.order_id, coffee, ctx=ctx_for("hub_employee"))
    asking = ctx_for(role, language="es")

    card = drawn(asking, session.order_id)["confirm"]

    assert (card["operation"], lines(card)) == (VOID, [("Cuenta abierta", "3 (Comedor)")])
    assert confirmed(asking, session.order_id) == ["ok"]
    assert state(table, session) == ("available", "voided")


def test_an_employee_confirms_the_card_of_an_empty_check_and_the_table_is_free(seated):
    table, session = seated
    asking = ctx_for("hub_employee", language="es")

    assert lines(drawn(asking, session.order_id)["confirm"]) == [("Cuenta abierta", "3 (Comedor)")]
    assert confirmed(asking, session.order_id) == ["ok"]
    assert state(table, session) == ("available", "voided")


def test_an_employee_never_sees_the_card_of_voiding_a_check_with_something_on_it(seated, coffee):
    """It is a manager's to approve (``sale.order.void_ordered``): the model hears the refusal before any card."""
    table, session = seated
    add_line(session.order_id, coffee, ctx=ctx_for("hub_employee"))

    plan = drawn(ctx_for("hub_employee", language="es"), session.order_id)

    assert plan["confirm"] is None
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("refused", "permission_denied")]
    assert state(table, session) == ("occupied", "open")


def test_a_role_that_may_never_void_is_told_before_any_card_and_offered_no_managers_door(seated, coffee, make_user):
    table, session = seated
    add_line(session.order_id, coffee, ctx=ctx_for("hub_employee"))
    user = make_user("saas:3", host=A.key, role=Membership.Role.EMPLOYEE)
    waiter = {"base__view_home": ON, "sale__view_sale": ON, "sale__add_sale": ON, "table__view_table": ON}
    held_by(user, a_role("No voids", sale__void_sale=OFF, **waiter))
    asking = OperationContext(scope=A, actor=user, permissions=access_for(user, A), language="es")
    tools = assistant.tools.catalog(asking)
    assert VOID in tools  # positive control: an empty check is still theirs to void
    assert "sale.order.void_ordered" not in tools

    plan = drawn(asking, session.order_id)

    assert plan["confirm"] is None
    assert [(row["outcome"], row["code"]) for row in plan["executed"]] == [("refused", "permission_denied")]
    assert state(table, session) == ("occupied", "open")
