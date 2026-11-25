"""What a manager may approve at the till, done by whoever may do it themselves (BASE-F85): who runs the business finds
it in Employees › Approvals with who did it and its figures, and nobody's approval. Once for each action: neither a
refusal nor the answer given again to the same request leaves another line. Over HTTP, as the till asks."""

import pytest
from django.core.cache import cache

from apps.sale.tests.conftest import HUB_DB
from apps.sale.tests.test_approvals import (
    approve,
    asked,
    cap,
    cashier,
    charge,
    code,
    coffee,
    eva,
    manager,
    open_check,
    post,
    refund_body,
    with_pass,
)
from base.models.approvals import Approval

__all__ = ["cashier", "coffee", "eva", "manager"]

pytestmark = HUB_DB


@pytest.fixture(autouse=True)
def no_brakes():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def till(client, manager):
    """Mario, who may do all of it himself, at the till."""
    client.force_login(manager)
    return client


def record() -> list[tuple]:
    rows = Approval.objects.order_by("created_at", "id")
    return [(row.operation, row.way, row.requested_by, row.approved_by, row.figures) for row in rows]


def by_mario(operation: str, figures: dict | None = None) -> tuple:
    return (operation, "role", "mario", "", figures)


def test_a_void_is_on_the_record_once_and_the_one_refused_is_not(till, coffee):
    sale = charge(till)
    body = {"sale_id": sale["id"], "reason": "Wrong table"}

    assert post(till, "/sale/sales/void", body).status_code == 200
    assert post(till, "/sale/sales/void", body).status_code == 409

    assert record() == [by_mario("sale.sale.void")]


def test_a_refund_is_on_the_record_once_though_its_request_is_sent_again(till, coffee):
    sale = charge(till)
    body = refund_body(sale, 100)

    first, again = (post(till, "/sale/sales/refund", body) for _ in range(2))

    assert (first.status_code, again.status_code) == (200, 200), again.content
    assert again.json()["already"] is True
    assert record() == [by_mario("sale.sale.refund")]


def test_a_discount_above_the_maximum_says_how_much_and_one_under_it_is_nothing_to_record(till, coffee):
    cap(10)
    order = open_check(till)
    body = {"order_id": order["id"], "line_id": order["lines"][0]["id"], "discount_percent": "50"}

    assert post(till, "/sale/orders/set_line_discount", {**body, "discount_percent": "5"}).status_code == 200
    assert code(post(till, "/sale/orders/set_line_discount", body)) == "sale.discount_over_limit"
    assert record() == []
    assert post(till, "/sale/orders/set_line_discount_over_limit", body).status_code == 200

    assert record() == [by_mario("sale.order.set_line_discount_over_limit", {"discount_percent": "50"})]


def test_a_charge_above_the_maximum_is_on_the_record_once_though_its_request_is_sent_again(till, coffee):
    cap(10)
    body = {
        "idempotency_key": "by-role-key-0001",
        "lines": [{"product": "COF"}],
        "discount_percent": "50",
        "payments": [{"method": "card"}],
    }

    first, again = (post(till, "/sale/sales/complete_over_limit", body) for _ in range(2))

    assert (first.status_code, again.status_code) == (201, 201), again.content
    assert first.json()["id"] == again.json()["id"]
    [row] = record()
    assert row[:4] == by_mario("sale.sale.complete_over_limit")[:4]
    assert row[4]["discount_percent"] == "50"


def test_an_open_price_and_a_check_deleted_with_something_on_it(till, coffee):
    order = open_check(till)
    body = {"order_id": order["id"], "unit_price": 420, "tax_category_key": "restaurant.food"}
    assert post(till, "/sale/orders/add_open_line", body).status_code == 200
    assert post(till, "/sale/orders/void_ordered", {"order_id": order["id"]}).status_code == 200

    assert record() == [by_mario("sale.order.add_open_line", {"unit_price": 420}), by_mario("sale.order.void_ordered")]


def test_what_a_manager_approves_for_the_cashier_is_on_it_once_with_who_approved(cashier, coffee):
    sale = charge(cashier)
    body = {"sale_id": sale["id"], "reason": "Wrong table"}
    token = approve(cashier, asked(post(cashier, "/sale/sales/void", body)))

    assert post(cashier, "/sale/sales/void", body, **with_pass(token)).status_code == 200

    assert record() == [("sale.sale.void", "pin", "eva", "mario", None)]


def test_a_sale_charged_as_any_other_is_nothing_to_record(till, coffee):
    charge(till)

    assert record() == []
