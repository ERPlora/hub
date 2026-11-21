"""Printing the bill of an open check for the table notes on the check that its bill was asked for (SALE-F21,
TABLE-F34): the plan of Tables reads it from there. The note belongs to the check, says so with the check's own
event in the same transaction, and only the check's end takes it away.

Without Printing in the business the bill is not queued and the device prints it: the note is taken all the same.
"""

import pytest
from live.errors import Conflict
from live.models import OutboxEvent

from apps.sale.models import Order
from apps.sale.services import printouts
from apps.sale.tests.conftest import HUB_DB, run

pytestmark = HUB_DB


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


def open_check(label: str = "Table 4"):
    return run("sale.order.open", {"lines": [{"product": "COF"}], "label": label})


def print_bill(order_id):
    return run("sale.order.print_bill", {"order_id": str(order_id)})


def printed_at(order_id):
    return Order.objects.get(pk=order_id).bill_printed_at


def changed(order_id) -> int:
    """How many times the outbox says the check changed."""
    return OutboxEvent.objects.filter(name="sale.order.changed", payload={"order_id": str(order_id)}).count()


def test_a_check_whose_bill_is_printed_is_noted_with_its_event(coffee):
    order = open_check()
    assert printed_at(order.id) is None
    print_bill(order.id)
    assert printed_at(order.id) is not None
    assert changed(order.id) == 1


def test_the_note_and_its_event_go_back_with_a_print_that_fails(coffee, monkeypatch):
    order = open_check()

    def broken(ctx, request):
        raise RuntimeError("the print broke")

    monkeypatch.setattr(printouts, "_queue_paper", broken)
    with pytest.raises(RuntimeError):
        print_bill(order.id)
    assert printed_at(order.id) is None
    assert changed(order.id) == 0


def test_printing_it_again_changes_nothing(coffee):
    order = open_check()
    print_bill(order.id)
    first = printed_at(order.id)
    print_bill(order.id)
    assert printed_at(order.id) == first
    assert changed(order.id) == 1


def test_the_note_leaves_the_version_the_till_charges_with(coffee):
    order = open_check()
    print_bill(order.id)
    assert Order.objects.get(pk=order.id).version == order.version
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "sale-bill-printed-charge",
            "order_id": str(order.id),
            "order_version": order.version,
            "payments": [{"method": "card"}],
        },
    )
    assert sale.total == 150 and Order.objects.get(pk=order.id).status == Order.Status.COMPLETED


def test_adding_lines_or_charging_part_keeps_the_note(coffee):
    order = open_check()
    print_bill(order.id)
    first = printed_at(order.id)
    added = run("sale.order.add_line", {"order_id": str(order.id), "product": "COF"})
    run(
        "sale.sale.complete",
        {
            "idempotency_key": "sale-bill-printed-part",
            "order_id": str(order.id),
            "line_ids": [str(added.lines[-1].id)],
            "payments": [{"method": "card"}],
        },
    )
    assert Order.objects.get(pk=order.id).status == Order.Status.OPEN
    assert printed_at(order.id) == first


def test_the_check_that_stays_after_a_merge_keeps_its_note(coffee):
    stays = open_check("Table 4")
    joins = open_check("Table 5")
    print_bill(stays.id)
    first = printed_at(stays.id)
    run("sale.order.merge", {"from_order_id": str(joins.id), "to_order_id": str(stays.id)})
    assert printed_at(stays.id) == first


def test_a_closed_check_is_not_noted(coffee):
    order = open_check()
    run("sale.order.void", {"order_id": str(order.id)})
    with pytest.raises(Conflict) as refusal:
        print_bill(order.id)
    assert refusal.value.code == "sale.order_changed"
    assert printed_at(order.id) is None
    assert changed(order.id) == 0
