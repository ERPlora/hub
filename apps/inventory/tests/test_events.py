"""The inventory app's events (``inventory.<entity>.<fact>``) and its reactions to the Sales app's events.

Here a reaction is tested by handing ``react`` the event as the outbox relay does: its name, its scope
and its payload. ``test_relay.py`` drives the same reactions end to end through the worker's real relay.
"""

import re
import uuid
from decimal import Decimal

import pytest
from live.context import Scope
from live.operations import NAME_RE

from apps.inventory import events
from apps.inventory.models import Product, StockMovement
from apps.tax.models import TaxCategory

PAST_FACT = re.compile(r"^inventory\.[a-z_]+\.[a-z_]+ed$")
A = Scope("host", "a")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("inventory.")
    }


def test_the_events_of_the_workbook_and_the_ones_that_refresh_the_screens():
    assert declared() == {
        "PRODUCT_CREATED": "inventory.product.created",
        "PRODUCT_UPDATED": "inventory.product.updated",
        "PRODUCT_DELETED": "inventory.product.deleted",
        "PRODUCT_CATEGORIZED": "inventory.product.categorized",
        "PRODUCT_UNCATEGORIZED": "inventory.product.uncategorized",
        "CATEGORY_CREATED": "inventory.category.created",
        "CATEGORY_UPDATED": "inventory.category.updated",
        "CATEGORY_DELETED": "inventory.category.deleted",
        "STOCK_CHANGED": "inventory.stock.changed",
        "STOCK_THRESHOLD_CROSSED": "inventory.stock.threshold_crossed",
        "CONFIG_UPDATED": "inventory.config.updated",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_it_reacts_to_a_paid_sale_a_voided_one_and_a_refund():
    # INVENTORY-F24 (2026-10-14): the units a refund brings back go back to the stock.
    assert events.REACTIONS == {
        "sale.sale.completed": "inventory.stock.apply_sale",
        "sale.sale.voided": "inventory.stock.restore_sale",
        "sale.sale.refunded": "inventory.stock.restore_refund",
    }


@pytest.mark.django_db
def test_a_paid_sale_and_its_void_reach_the_stock_as_the_system():
    tax = TaxCategory.objects.create(key="test.general", name="General")
    coffee = Product.objects.create(name="Coffee", sku="CAF", price=100, tax_category=tax, stock=Decimal("10"))
    sale = uuid.uuid7()
    # What Sales records, with more than inventory reads: the rest is ignored.
    paid = {"sale_id": str(sale), "number": "T-1", "items": [{"product_id": str(coffee.id), "quantity": "3", "price": 100}]}

    first = events.react(A, "sale.sale.completed", paid)
    again = events.react(A, "sale.sale.completed", paid)

    assert (first.state, first.applied, again.applied) == ("moved", True, False)
    assert Product.objects.get().stock == Decimal("7")
    assert StockMovement.objects.get(movement_type="sale").actor == "system"
    assert events.react(A, "sale.sale.voided", {"sale_id": str(sale)}).movements == 1
    assert Product.objects.get().stock == Decimal("10")


@pytest.mark.django_db
def test_an_event_it_does_not_react_to_does_nothing():
    assert events.react(A, "sale.sale.reassigned", {"sale_id": str(uuid.uuid7())}) is None
    assert events.react(A, "customer.customer.created", {}) is None


# INVENTORY-F24 with the Sales app's REAL events: the sale is paid and refunded through its own
# operations and its outbox payload goes to ``react``, as the relay does. The sale app is
# imported here only, in the tests: Inventory does not depend on it.


def _sale_run(name: str, data: dict):
    from apps.sale.tests.conftest import run

    return run(name, data)


def _last_payload(name: str) -> dict:
    from live.models import OutboxEvent

    return OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first().payload


@pytest.mark.django_db
def test_a_refund_puts_the_returned_units_back_once_as_the_system():
    from live.context import system_context
    from live.operations import get

    create = get("inventory.product.create")
    create(
        system_context(A),
        create.input.model_validate(
            {"name": "Coffee", "sku": "COF", "price": 1210, "tax_category_key": "product.generic", "initial_stock": "10"}
        ),
    )
    sale = _sale_run("sale.sale.complete", {"idempotency_key": "inv-refund-0001", "lines": [{"product": "COF", "quantity": "3"}], "payments": [{"method": "card"}]})
    events.react(A, "sale.sale.completed", _last_payload("sale.sale.completed"))
    assert Product.objects.get(sku="COF").stock == Decimal("7")

    _sale_run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "two cups back",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 2420}],
            "lines": [{"line_id": str(sale.lines[0].id), "quantity": "2"}],
        },
    )
    payload = _last_payload("sale.sale.refunded")
    first = events.react(A, "sale.sale.refunded", payload)
    again = events.react(A, "sale.sale.refunded", payload)

    assert (str(first.refund_id), first.applied, first.movements) == (payload["refund_id"], True, 1)
    assert (again.applied, again.movements) == (False, 0)
    assert Product.objects.get(sku="COF").stock == Decimal("9")
    movement = StockMovement.objects.get(movement_type="refund")
    assert (movement.qty, movement.reference, movement.reason, movement.actor) == (Decimal("2"), str(sale.id), "two cups back", "system")
