"""Voiding an open check is checked before the assistant draws its card (SALE-F18, BASE-F97): an empty check is
whoever builds checks' to void, one with something on it needs the void permission. Whoever lacks it never confirms a
card that is then refused: the model hears the refusal first, with the code the till answers with a manager's approval,
and the manager's door (``sale.order.void_ordered``) is what a manager approves."""

import pytest
from live.errors import NotFound, PermissionDenied
from live.operations import INTERNAL, get

from apps.sale.models import Order
from apps.sale.tests.conftest import HUB_DB, ctx_for, run
from base import assistant

pytestmark = HUB_DB

VOID = "sale.order.void"
CHECK = "sale.order.check_void"


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 150, "restaurant.drink")


def a_check(*products) -> str:
    order_id = str(run("sale.order.open", {"label": "Mesa 3"}).id)
    for product in products:
        run("sale.order.add_line", {"order_id": order_id, "product_id": str(product.id), "quantity": "1"})
    return order_id


def checked(role: str, order_id: str):
    return run(CHECK, {"order_id": order_id}, ctx_for(role))


def test_the_void_is_checked_before_its_card_and_the_check_is_no_tool():
    assert assistant.cards.check_of(get(VOID)) == CHECK
    assert get(CHECK).ai is INTERNAL


@pytest.mark.parametrize("role", ["hub_employee", "hub_manager"])
def test_whoever_builds_checks_may_void_an_empty_one(role):
    order_id = a_check()
    assert str(checked(role, order_id).id) == order_id


def test_a_manager_may_void_a_check_with_something_on_it(coffee):
    order_id = a_check(coffee)
    assert str(checked("hub_manager", order_id).id) == order_id


def test_whoever_lacks_the_void_permission_is_refused_a_check_with_something_on_it(coffee):
    order_id = a_check(coffee)
    with pytest.raises(PermissionDenied) as refused:
        checked("hub_employee", order_id)
    assert refused.value.code == "permission_denied"


@pytest.mark.parametrize("status", ["completed", "voided"])
def test_a_check_no_longer_open_is_the_voids_to_answer_whoever_asks(coffee, status):
    # The void answers that a check is no longer open before it looks at who asks: no manager is called for it.
    order_id = a_check(coffee)
    Order.objects.filter(pk=order_id).update(status=status)
    assert str(checked("hub_employee", order_id).id) == order_id


def test_a_check_that_does_not_exist_is_not_found():
    with pytest.raises(NotFound):
        checked("hub_manager", "01960000-0000-7000-8000-000000000000")
