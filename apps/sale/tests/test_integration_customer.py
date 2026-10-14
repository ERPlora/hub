"""Sale and Customers together, no mocks: the customer of a sale, its link to the open check, and the
purchase history the sale's real events write through Customers' real operations.

Customers wires its reactions once the outbox relay delivers events between apps (phase 2): here the
sale's real event payload is handed to ``customer.purchase.record`` / ``void``, the operations those
reactions run.
"""

import pytest
from live.context import system_context
from live.models import OutboxEvent
from live.operations import get

from apps.customer.models import Customer
from apps.sale.tests.conftest import A, run

pytestmark = pytest.mark.django_db


def deliver(event_name: str, operation_name: str):
    event = (
        OutboxEvent.objects.filter(name=event_name)
        .order_by("-created_at", "-id")
        .first()
    )
    reaction = get(operation_name)
    return reaction(system_context(A), reaction.input.model_validate(event.payload))


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 1210, "product.generic")


def test_a_paid_sale_adds_to_its_customers_history(coffee, customer):
    ana = customer("Ana López", phone="600111222")
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "cus-sale-0001",
            "lines": [{"product": "COF", "quantity": "2"}],
            "customer": "600 111 222",
        },
    )
    assert (sale.customer_id, sale.customer_name) == (ana.id, "Ana López")
    recorded = deliver("sale.sale.completed", "customer.purchase.record")
    assert recorded.recorded is True
    card = Customer.objects.get(pk=ana.id)
    assert (card.total_purchases, card.total_spent) == (1, 2420)
    # The same sale delivered twice counts once.
    assert deliver("sale.sale.completed", "customer.purchase.record").recorded is False


def test_a_voided_sale_is_taken_off_the_history(coffee, customer):
    ana = customer("Ana López")
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "cus-sale-0001",
            "lines": [{"product": "COF"}],
            "customer_id": str(ana.id),
        },
    )
    deliver("sale.sale.completed", "customer.purchase.record")
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong customer"})
    assert deliver("sale.sale.voided", "customer.purchase.void").voided is True
    card = Customer.objects.get(pk=ana.id)
    assert (card.total_purchases, card.total_spent) == (0, 0)


def test_a_sale_without_customer_records_nothing(coffee):
    run(
        "sale.sale.complete",
        {"idempotency_key": "cus-sale-0001", "lines": [{"product": "COF"}]},
    )
    assert deliver("sale.sale.completed", "customer.purchase.record").recorded is False


def test_the_customer_of_an_open_check_is_kept_by_customers(coffee, customer):
    ana = customer("Ana López")
    order = run("sale.order.open", {"lines": [{"product": "COF"}]})
    run("customer.order.link", {"order_id": str(order.id), "customer_id": str(ana.id)})
    # The till puts her back when the check is picked up again.
    assert (
        run("customer.order.customer", {"order_id": str(order.id)}).customer_id
        == ana.id
    )
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "cus-sale-0001",
            "order_id": str(order.id),
            "customer_id": str(ana.id),
        },
    )
    assert sale.customer_id == ana.id


def test_an_erased_customer_keeps_the_sales_printed_name(coffee, customer):
    ana = customer("Ana López")
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "cus-sale-0001",
            "lines": [{"product": "COF"}],
            "customer_id": str(ana.id),
        },
    )
    run("customer.customer.erase", {"id": str(ana.id), "reason": "GDPR request"})
    found = run("sale.sale.get", {"sale_id": str(sale.id)})
    # A sale is a fiscal record: its copy of the name stays (WORKBOOK «Dudas abiertas»).
    assert found.customer_name == "Ana López" and found.customer_id == ana.id
