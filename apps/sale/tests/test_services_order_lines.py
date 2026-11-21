"""Comping a line the kitchen already has (SALE-F15, F20).

What is comped is usually what was already served: the dessert on the house or the dish that came out
wrong. A sent line takes the comp, or loses it, with the same permission as any other line; the
kitchen gets nothing new, and its quantity and note stay as the kitchen received them.
"""

import pytest
from live.errors import Conflict
from live.models import OutboxEvent

from apps.sale.models import OrderLine
from apps.sale.tests.conftest import HUB_DB, ctx_for, run

pytestmark = HUB_DB

EMPLOYEE = "hub_employee"


@pytest.fixture
def sent(product):
    """An open check whose only line, a 6.50 € dessert, is already in the kitchen."""
    product("Cheesecake", "CHK", 650, "restaurant.food")
    order = run("sale.order.open", {"lines": [{"product": "CHK"}]})
    run("sale.order.fire", {"order_id": str(order.id)})
    return {"order_id": str(order.id), "line_id": str(order.lines[0].id)}


def sale_events() -> list[str]:
    return list(
        OutboxEvent.objects.filter(name__startswith="sale.")
        .order_by("created_at", "id")
        .values_list("name", flat=True)
    )


def test_an_employee_comps_a_sent_line_and_the_kitchen_gets_nothing_new(sent):
    OutboxEvent.objects.all().delete()
    comped = run(
        "sale.order.update_line",
        {**sent, "is_gift": True, "gift_reason": "On the house"},
        ctx_for(EMPLOYEE),
    )
    line = comped.lines[0]
    assert (line.is_gift, line.gift_reason, line.line_total) == (True, "On the house", 0)
    assert (line.round_no, line.fired_at is not None) == (1, True)
    assert comped.provisional_total == 0
    assert sale_events() == ["sale.order.changed"]


def test_a_comped_sent_line_is_charged_again_when_the_comp_is_taken_off(sent):
    run("sale.order.update_line", {**sent, "is_gift": True, "gift_reason": "On the house"})
    back = run("sale.order.update_line", {**sent, "is_gift": False}, ctx_for(EMPLOYEE))
    line = back.lines[0]
    assert (line.is_gift, line.gift_reason, line.line_total) == (False, "", 650)
    assert back.provisional_total == 650


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "2"},
        {"notes": "no sugar"},
        {"is_gift": True, "quantity": "2"},
        {"is_gift": True, "notes": "no sugar"},
    ],
)
def test_a_sent_line_keeps_the_quantity_and_note_the_kitchen_received(sent, change):
    with pytest.raises(Conflict) as refusal:
        run("sale.order.update_line", {**sent, **change})
    assert refusal.value.code == "sale.order_line_not_available"
    row = OrderLine.objects.get(pk=sent["line_id"])
    assert (row.quantity, row.notes, row.is_gift) == (1, "", False)
