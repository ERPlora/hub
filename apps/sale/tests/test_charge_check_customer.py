"""Charging an open check that has a customer, without naming her: the sale is hers, as when the till picks the check
up again and charges it. The assistant and the API send no customer unless told; Customers keeps who the check is
for (CUSTOMER-F19), and the charge reads it there."""

import json

import pytest
from live.models import OutboxEvent

from apps.customer import events as customer_events
from apps.customer.models import Customer
from apps.sale.models.sales import Sale
from apps.sale.tests.conftest import HUB_DB, A, charged_by_the_assistant, run

pytestmark = HUB_DB


@pytest.fixture
def coffee(product):
    return product("Coffee", "COF", 180, "product.generic")


@pytest.fixture
def lucia(customer):
    return customer("Lucía Martín", phone="600111222")


def open_check(customer_card=None, *lines):
    order = run("sale.order.open", {"lines": list(lines) or [{"product": "COF", "quantity": "2"}]})
    if customer_card is not None:
        run("customer.order.link", {"order_id": str(order.id), "customer_id": str(customer_card.id)})
    return order


def charge(order, key="check-charge-0001", **more):
    return run("sale.sale.complete", {"idempotency_key": key, "order_id": str(order.id), **more})


def delivered_purchase():
    event = OutboxEvent.objects.filter(name="sale.sale.completed").order_by("-created_at", "-id").first()
    return customer_events.react(A, event.name, event.payload)


def test_the_assistant_charging_a_check_with_a_customer_leaves_the_sale_and_the_purchase_hers(coffee, lucia):
    order = open_check(lucia)
    outcome = charged_by_the_assistant(order)
    sale = Sale.objects.get(order_id=order.id)
    assert (sale.customer_id, sale.customer_name) == (lucia.id, "Lucía Martín")
    assert json.loads(outcome.content)["customer_id"] == str(lucia.id)
    assert delivered_purchase().recorded is True
    card = Customer.objects.get(pk=lucia.id)
    assert (card.total_purchases, card.total_spent) == (1, 360)


def test_the_api_charging_a_check_by_card_without_naming_its_customer_charges_it_to_her(coffee, lucia):
    sale = charge(open_check(lucia), payments=[{"method": "card"}])
    assert (sale.customer_id, sale.customer_name) == (lucia.id, "Lucía Martín")


def test_a_partial_charge_of_a_check_is_its_customers_too(coffee, lucia):
    order = open_check(lucia, {"product": "COF"}, {"product": "COF"})
    first = run("sale.order.get", {"order_id": str(order.id)}).lines[0]
    sale = charge(order, line_ids=[str(first.id)])
    assert sale.customer_id == lucia.id


@pytest.mark.parametrize("named", ["by_id", "by_phone"])
def test_the_customer_named_at_the_charge_is_the_sales_not_the_checks(coffee, lucia, customer, named):
    pedro = customer("Pedro Ruiz", phone="600333444")
    said = {"customer_id": str(pedro.id)} if named == "by_id" else {"customer": "600 333 444"}
    sale = charge(open_check(lucia), **said)
    assert (sale.customer_id, sale.customer_name) == (pedro.id, "Pedro Ruiz")


def test_a_check_its_customer_was_taken_off_is_charged_without_one(coffee, lucia):
    order = open_check(lucia)
    run("customer.order.link", {"order_id": str(order.id), "customer_id": None})
    sale = charge(order)
    assert (sale.customer_id, sale.customer_name) == (None, "")


def test_a_check_whose_customer_was_deleted_is_charged_without_one(coffee, lucia):
    order = open_check(lucia)
    run("customer.customer.delete", {"id": str(lucia.id)})
    sale = charge(order)
    assert sale.customer_id is None


def test_a_business_that_requires_a_customer_charges_a_check_that_has_one(coffee, lucia):
    run("sale.settings.update", {"require_customer": True})
    sale = charge(open_check(lucia))
    assert sale.customer_id == lucia.id


def test_a_check_without_a_customer_is_charged_without_one_whoever_the_others_are_for(coffee, lucia):
    open_check(lucia)
    sale = charge(open_check())
    assert sale.customer_id is None
