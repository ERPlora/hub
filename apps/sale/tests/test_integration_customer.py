"""Sale and Customers together, no mocks: the customer of a sale, its link to the open check, and the
purchase history the sale's real events write on its card.

The sale's real event (``sale.sale.completed`` / ``voided`` / ``refunded``, as recorded in the outbox)
is handed to Customers' real reaction (``apps.customer.events.react``), as the outbox relay will in
phase 2.
"""

import pytest
from live.models import OutboxEvent

from apps.customer import events as customer_events
from apps.customer.models import Customer
from apps.sale.tests.conftest import A, run

pytestmark = pytest.mark.django_db


def deliver(name: str):
    """Hands the newest ``name`` event of the outbox to Customers, as the relay will."""
    event = OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()
    return customer_events.react(A, event.name, event.payload)


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
    recorded = deliver("sale.sale.completed")
    assert recorded.recorded is True
    card = Customer.objects.get(pk=ana.id)
    assert (card.total_purchases, card.total_spent) == (1, 2420)
    # The same sale delivered twice counts once.
    assert deliver("sale.sale.completed").recorded is False


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
    deliver("sale.sale.completed")
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong customer"})
    assert deliver("sale.sale.voided").voided is True
    card = Customer.objects.get(pk=ana.id)
    assert (card.total_purchases, card.total_spent) == (0, 0)


def test_a_refund_comes_off_its_customers_spend_once(coffee, customer):
    ana = customer("Ana López")
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "cus-sale-0001",
            "lines": [{"product": "COF", "quantity": "2"}],
            "customer_id": str(ana.id),
        },
    )
    deliver("sale.sale.completed")
    run(
        "sale.sale.refund",
        {
            "idempotency_key": "cus-refund-0001",
            "sale_id": str(sale.id),
            "lines": [{"line_id": str(sale.lines[0].id), "quantity": "1"}],
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 1210}],
            "reason": "one was cold",
        },
    )
    assert deliver("sale.sale.refunded").refunded is True
    card = Customer.objects.get(pk=ana.id)
    assert (card.total_purchases, card.total_spent) == (1, 1210)
    # The same refund delivered twice comes off once.
    assert deliver("sale.sale.refunded").refunded is False
    assert Customer.objects.get(pk=ana.id).total_spent == 1210


def test_a_sale_without_customer_records_nothing(coffee):
    run(
        "sale.sale.complete",
        {"idempotency_key": "cus-sale-0001", "lines": [{"product": "COF"}]},
    )
    assert deliver("sale.sale.completed").recorded is False


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
