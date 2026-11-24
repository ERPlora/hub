"""Charging an open check with dishes not sent to the kitchen yet: the charge sends them first, as the till's «Charge»
does (SALE-F20), so nobody pays for a dish the kitchen never gets. The assistant and the API charge with that same
operation; a send that fails charges nothing."""

import pytest
from live.context import OperationContext
from live.errors import Conflict, PermissionDenied

from apps.kitchen.services import rounds
from apps.sale.models import Order, OrderLine, Sale
from apps.sale.tests.conftest import HUB_DB, charged_by_the_assistant, ctx_for, run

pytestmark = HUB_DB


@pytest.fixture
def flan(product):
    return product("Home-made flan", "FLAN", 450, "restaurant.food")


@pytest.fixture
def coffee(product):
    return product("White coffee", "WCOF", 180, "restaurant.drink")


def open_check(*skus, label="Table 4"):
    return run("sale.order.open", {"label": label, "lines": [{"product": sku} for sku in skus]})


def sent(order):
    """What the kitchen has of the check: each round's ticket with the names of its dishes."""
    tickets = run("kitchen.ticket.by_order", {"order_id": str(order.id)}).tickets
    return sorted((ticket.round_no, sorted(item.name for item in ticket.items)) for ticket in tickets)


def unsent(order):
    return OrderLine.objects.filter(order_id=order.id, fired_at__isnull=True).count()


def charge(order, key="kitchen-charge-0001", ctx=None, **more):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "order_id": str(order.id), "payments": [{"method": "cash"}], **more},
        ctx,
    )


def test_the_assistant_charging_a_check_with_an_unsent_dish_sends_it_to_the_kitchen_first(flan):
    order = open_check("FLAN", "FLAN")
    charged_by_the_assistant(order)
    assert Sale.objects.filter(order_id=order.id).count() == 1
    assert sent(order) == [(1, ["Home-made flan", "Home-made flan"])]
    assert unsent(order) == 0


def test_the_api_charge_sends_what_is_left_as_a_new_round_after_the_ones_sent(flan, coffee):
    order = open_check("FLAN")
    run("kitchen.ticket.send", {"order_id": str(order.id)})
    run("sale.order.add_line", {"order_id": str(order.id), "product": "WCOF"})
    charge(order, payments=[{"method": "card"}])
    assert sent(order) == [(1, ["Home-made flan"]), (2, ["White coffee"])]
    assert Order.objects.get(pk=order.id).status == Order.Status.COMPLETED


def test_the_managers_charge_above_the_discount_cap_sends_first_too(flan):
    order = open_check("FLAN")
    run(
        "sale.sale.complete_over_limit",
        {"idempotency_key": "over-limit-0001", "order_id": str(order.id), "payments": [{"method": "cash"}]},
    )
    assert sent(order) == [(1, ["Home-made flan"])]


def test_the_version_the_screen_charged_still_charges_after_the_charge_sent_the_round(flan):
    order = open_check("FLAN")
    seen = run("sale.order.get", {"order_id": str(order.id)}).version
    sale = charge(order, order_version=seen)
    assert sale.order_id == order.id
    assert sent(order) == [(1, ["Home-made flan"])]


def test_a_check_whose_version_changed_since_the_screen_read_it_sends_nothing_and_charges_nothing(flan, coffee):
    order = open_check("FLAN")
    seen = run("sale.order.get", {"order_id": str(order.id)}).version
    run("sale.order.add_line", {"order_id": str(order.id), "product": "WCOF"})
    with pytest.raises(Conflict) as refused:
        charge(order, order_version=seen)
    assert refused.value.code == "sale.order_changed"
    assert (sent(order), unsent(order)) == ([], 2)


def test_a_check_already_sent_is_charged_without_another_round(flan):
    order = open_check("FLAN")
    run("kitchen.ticket.send", {"order_id": str(order.id)})
    charge(order)
    assert sent(order) == [(1, ["Home-made flan"])]


def test_charging_the_same_attempt_again_sends_nothing_twice(flan):
    order = open_check("FLAN")
    first = charge(order)
    again = charge(order)
    assert again.id == first.id
    assert sent(order) == [(1, ["Home-made flan"])]


def test_retrying_a_partial_charge_sends_nothing_added_since(flan, coffee):
    order = open_check("FLAN", "FLAN")
    first = run("sale.order.get", {"order_id": str(order.id)}).lines[0]
    charged = charge(order, line_ids=[str(first.id)])
    run("sale.order.add_line", {"order_id": str(order.id), "product": "WCOF"})
    again = charge(order, line_ids=[str(first.id)])
    assert again.id == charged.id
    assert sent(order) == [(1, ["Home-made flan", "Home-made flan"])]
    assert unsent(order) == 1


def test_a_partial_charge_sends_everything_pending_as_the_till_does(flan, coffee):
    order = open_check("FLAN", "WCOF")
    first = run("sale.order.get", {"order_id": str(order.id)}).lines[0]
    charge(order, line_ids=[str(first.id)])
    assert sent(order) == [(1, ["Home-made flan", "White coffee"])]


def test_a_send_that_is_refused_charges_nothing_and_says_why(flan):
    order = open_check("FLAN")
    admin = ctx_for()
    cannot_fire = OperationContext(scope=admin.scope, actor="cashier", permissions=admin.permissions - {"sale.add_sale"})
    with pytest.raises(PermissionDenied) as refused:
        charge(order, ctx=cannot_fire)
    assert "sale.add_sale" in str(refused.value)
    assert not Sale.objects.filter(order_id=order.id).exists()
    assert (sent(order), unsent(order)) == ([], 1)


def test_when_the_kitchen_has_nothing_to_cook_the_check_is_charged_as_the_till_does(flan, monkeypatch):
    # What the kitchen answers for a menu of services only: the till charges it all the same.
    order = open_check("FLAN")
    monkeypatch.setattr(rounds, "_round_ticket", lambda line_ids: None)
    charge(order)
    assert Order.objects.get(pk=order.id).status == Order.Status.COMPLETED
    assert (sent(order), unsent(order)) == ([], 1)


def test_without_kitchen_the_check_is_charged_as_always(flan, without_kitchen):
    order = open_check("FLAN")
    charge(order)
    assert Order.objects.get(pk=order.id).status == Order.Status.COMPLETED
    assert unsent(order) == 1


def test_a_cashier_who_cannot_send_to_the_kitchen_charges_as_her_till_does(flan):
    order = open_check("FLAN")
    admin = ctx_for()
    cashier = OperationContext(
        scope=admin.scope, actor="cashier", permissions=admin.permissions - {"kitchen.add_ticket"}
    )
    charge(order, ctx=cashier)
    assert Order.objects.get(pk=order.id).status == Order.Status.COMPLETED
    assert (sent(order), unsent(order)) == ([], 1)


def test_a_charge_refused_after_the_send_leaves_nothing_sent(flan):
    # An invoice without its recipient is refused once the round is out: the round goes back with the charge.
    order = open_check("FLAN")
    with pytest.raises(Conflict) as refused:
        charge(order, document_type="invoice")
    assert refused.value.code == "sale.invoice_recipient_incomplete"
    assert not Sale.objects.filter(order_id=order.id).exists()
    assert (sent(order), unsent(order)) == ([], 1)
