"""A cashier without voids (SALE-F30, SALE-F31, BASE-F84): what their role of the business says of each of the till's
actions a manager may approve. Allowed, it is done; with approval, the till asks a manager; with a no it is refused, with
nobody's PIN in between. Over HTTP, as the till asks."""

import pytest
from django.core.cache import cache

from apps.sale.models.orders import Order
from apps.sale.models.sales import Sale
from apps.sale.tests.conftest import HUB_DB
from apps.sale.tests.test_approvals import (
    approve,
    asked,
    cashier,
    charge,
    code,
    coffee,
    eva,
    events,
    manager,
    open_check,
    post,
    refund_body,
    with_pass,
)
from base.models import Membership
from base.models.approvals import Approval
from base.models.roles import BusinessRole
from base.permissions import permissions_of_role
from base.roles import APPROVAL, OFF, ON
from base.tests.roles import held_by

__all__ = ["cashier", "coffee", "eva", "manager"]

pytestmark = HUB_DB

VOID, REFUND = "sale.void_sale", "sale.refund_sale"


@pytest.fixture(autouse=True)
def no_brakes():
    cache.clear()
    yield
    cache.clear()


def given(user, **states) -> BusinessRole:
    """«Cashier without voids»: an employee's role, its voids and refunds as ``states`` says."""
    employee = dict.fromkeys(permissions_of_role(Membership.Role.EMPLOYEE), ON)
    role = BusinessRole.objects.create(
        name="Cashier without voids",
        origin=Membership.Role.EMPLOYEE,
        states=employee | {name.replace("__", "."): state for name, state in states.items()},
    )
    held_by(user, role)
    return role


def change(role: BusinessRole, permission: str, state: str) -> None:
    role.states = {**role.states, permission: state}
    role.save()


def void_body(sale: dict) -> dict:
    return {"sale_id": sale["id"], "reason": "Wrong table"}


OUTCOMES = [(ON, 200, None), (APPROVAL, 403, "requires_elevation"), (OFF, 403, "permission_denied")]


class TestVoid:
    @pytest.mark.parametrize(("state", "status", "why"), OUTCOMES)
    def test_a_charged_sale_is_voided_as_the_role_says(self, cashier, eva, coffee, state, status, why):
        given(eva, sale__void_sale=state)
        sale = charge(cashier)

        response = post(cashier, "/sale/sales/void", void_body(sale))

        assert response.status_code == status, response.content
        assert why is None or code(response) == why
        assert Sale.objects.get(pk=sale["id"]).status == ("voided" if state == ON else "completed")
        assert len(events("sale.sale.voided")) == (1 if state == ON else 0)

    def test_with_approval_the_managers_pin_voids_it(self, cashier, eva, coffee):
        given(eva, sale__void_sale=APPROVAL)
        sale = charge(cashier)
        token = approve(cashier, asked(post(cashier, "/sale/sales/void", void_body(sale))))

        assert post(cashier, "/sale/sales/void", void_body(sale), **with_pass(token)).status_code == 200

    def test_with_a_no_not_even_a_pass_given_before_voids_it(self, cashier, eva, coffee):
        role = given(eva, sale__void_sale=APPROVAL)
        sale = charge(cashier)
        token = approve(cashier, asked(post(cashier, "/sale/sales/void", void_body(sale))))

        change(role, VOID, OFF)

        assert code(post(cashier, "/sale/sales/void", void_body(sale), **with_pass(token))) == "permission_denied"
        assert Sale.objects.get(pk=sale["id"]).status == "completed"
        assert Approval.objects.get().used_at is None

    def test_a_no_to_void_is_also_one_to_what_else_voids(self, cashier, eva, coffee):
        """A line sent to the kitchen and an open check with something on it ask for the same permission."""
        given(eva, sale__void_sale=OFF)
        order = open_check(cashier)
        assert post(cashier, "/sale/orders/fire", {"order_id": order["id"]}).status_code == 200
        line = {"order_id": order["id"], "line_id": order["lines"][0]["id"], "reason": "Agotado"}

        assert code(post(cashier, "/sale/orders/void_line", line)) == "permission_denied"
        assert code(post(cashier, "/sale/orders/void_ordered", {"order_id": order["id"]})) == "permission_denied"
        assert Order.objects.get(pk=order["id"]).status == "open"


class TestRefund:
    @pytest.mark.parametrize(("state", "status", "why"), OUTCOMES)
    def test_a_charged_sale_is_refunded_as_the_role_says(self, cashier, eva, coffee, state, status, why):
        given(eva, sale__refund_sale=state)
        sale = charge(cashier)

        response = post(cashier, "/sale/sales/refund", refund_body(sale, 150))

        assert response.status_code == status, response.content
        assert why is None or code(response) == why
        assert Sale.objects.get(pk=sale["id"]).refunded_total == (150 if state == ON else 0)

    def test_a_no_to_void_leaves_refunds_as_they_are(self, cashier, eva, coffee):
        given(eva, sale__void_sale=OFF, sale__refund_sale=APPROVAL)
        sale = charge(cashier)

        assert code(post(cashier, "/sale/sales/void", void_body(sale))) == "permission_denied"
        asked(post(cashier, "/sale/sales/refund", refund_body(sale, 150)))


def test_the_cashier_of_the_invitation_is_still_asked(cashier, coffee):
    sale = charge(cashier)

    asked(post(cashier, "/sale/sales/void", void_body(sale)))
    asked(post(cashier, "/sale/sales/refund", refund_body(sale, 150)))
