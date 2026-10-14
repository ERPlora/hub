"""Sale and Inventory together, no mocks: the catalog that prices a line and the stock a sale moves.

The sale's real event (``sale.sale.completed`` / ``voided``, as recorded in the outbox) is handed to
Inventory's real reaction (``apps.inventory.events.react``), as the outbox relay will in phase 2.
"""

from decimal import Decimal

import pytest
from live.context import system_context
from live.errors import Conflict
from live.models import OutboxEvent

from apps.inventory import events as inventory_events
from apps.inventory.models import Product, StockMovement
from apps.sale.tests.conftest import A, run

pytestmark = pytest.mark.django_db


def deliver(name: str):
    """Hands the newest ``name`` event of the outbox to Inventory, as the relay will."""
    event = OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first()
    return inventory_events.react(A, event.name, event.payload)


def stock(sku: str) -> Decimal:
    return Product.objects.get(sku=sku, is_deleted=False).stock


@pytest.fixture
def shelf():
    make = lambda **data: run("inventory.product.create", data, system_context(A))  # noqa: E731
    make(
        name="Shampoo",
        sku="SHA",
        price=1200,
        tax_category_key="product.generic",
        initial_stock="10",
    )
    make(
        name="Wax",
        sku="WAX",
        price=900,
        tax_category_key="product.generic",
        initial_stock="5",
    )
    make(
        name="Haircut",
        sku="CUT",
        price=1800,
        tax_category_key="service.generic",
        product_type="service",
    )
    make(
        name="Olives",
        sku="OLV",
        price=1500,
        tax_category_key="product.reduced",
        unit="kg",
        initial_stock="3",
    )


def test_a_paid_sale_lowers_the_stock_of_each_article_once(shelf):
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "inv-sale-0001",
            "lines": [
                {"product": "SHA", "quantity": "2"},
                {"product": "WAX", "is_gift": True},
                {"product": "CUT"},
                {"product": "OLV", "quantity": "0.250"},
            ],
            "payments": [{"method": "card"}],
        },
    )
    result = deliver("sale.sale.completed")
    assert result.applied is True and result.movements == 3
    # The comp leaves the shelf too; the service moves nothing; the olives go by the gram.
    assert (stock("SHA"), stock("WAX"), stock("OLV")) == (
        Decimal("8.000"),
        Decimal("4.000"),
        Decimal("2.750"),
    )
    assert set(
        StockMovement.objects.filter(movement_type="sale").values_list(
            "reference", flat=True
        )
    ) == {str(sale.id)}
    # A repeated delivery moves nothing.
    assert deliver("sale.sale.completed").applied is False
    assert stock("SHA") == Decimal("8.000")


def test_a_voided_sale_gives_back_what_it_took(shelf):
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "inv-sale-0001",
            "lines": [{"product": "SHA", "quantity": "3"}],
            "payments": [{"method": "card"}],
        },
    )
    deliver("sale.sale.completed")
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "wrong ticket"})
    result = deliver("sale.sale.voided")
    assert result.applied is True
    assert stock("SHA") == Decimal("10.000")


def test_a_product_that_needs_its_tax_setup_is_not_sold_and_nothing_moves(shelf):
    Product.objects.filter(sku="WAX").update(tax_category=None)
    with pytest.raises(Conflict) as refusal:
        run(
            "sale.sale.complete",
            {"idempotency_key": "inv-sale-0001", "lines": [{"product": "WAX"}]},
        )
    assert refusal.value.code == "sale.tax_category_missing"
    assert not OutboxEvent.objects.filter(name="sale.sale.completed").exists()
    assert stock("WAX") == Decimal("5.000")


def test_the_line_takes_the_catalogs_price_unit_and_category(shelf):
    order = run("sale.order.open", {"lines": [{"product": "OLV", "quantity": "0.5"}]})
    line = order.lines[0]
    assert (line.unit, line.unit_price, line.tax_category_key, line.line_total) == (
        "kg",
        1500,
        "product.reduced",
        750,
    )
    assert line.product_id == Product.objects.get(sku="OLV").id


def test_an_article_that_is_deleted_can_no_longer_be_sold(shelf):
    run("inventory.product.delete", {"product": "SHA"}, system_context(A))
    with pytest.raises(Conflict) as refusal:
        run("sale.order.open", {"lines": [{"product": "SHA"}]})
    assert refusal.value.code == "sale.product_not_available"
