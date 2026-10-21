"""Sale and Inventory together, no mocks: the catalog that prices a line and the stock a sale moves.

The sale's real event (``sale.sale.completed`` / ``voided``, as recorded in the outbox) is handed to
Inventory's real reaction (``apps.inventory.events.react``), as the outbox relay will in phase 2.
"""

from decimal import Decimal

import pytest
from django.utils import translation
from live.context import system_context
from live.errors import Conflict
from live.models import OutboxEvent

from apps.inventory import events as inventory_events
from apps.inventory.models import Product, StockMovement
from apps.sale.models import Order, OrderLine, Sale
from apps.sale.tests.conftest import A, ctx_for, run

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


# ── Sold out («86», INVENTORY-F29; SALE-F07) ─────────────────────────────────────────────────────


def sold_out(sku: str, flag: bool = True) -> None:
    run("inventory.product.set_sold_out", {"product": sku, "sold_out": flag}, system_context(A))


# Every door that freezes a NEW line of the catalog: the screen's, the API's and the assistant's (which
# names the article as a person says it, by its name).
NEW_LINE_DOORS = {
    "preview": lambda line: run("sale.checkout.preview", {"lines": [line]}),
    "open": lambda line: run("sale.order.open", {"label": "Bar", "lines": [line]}),
    "add_line": lambda line: run(
        "sale.order.add_line", {"order_id": str(run("sale.order.open", {"label": "Bar"}).id), **line}
    ),
    "counter_charge": lambda line: run(
        "sale.sale.complete",
        {"idempotency_key": "inv-sold-0001", "lines": [line], "payments": [{"method": "card"}]},
    ),
}


@pytest.mark.parametrize("door", NEW_LINE_DOORS)
@pytest.mark.parametrize("named", [{"product": "SHA"}, {"product": "Shampoo"}], ids=["sku", "name"])
def test_a_sold_out_article_is_refused_as_a_new_line_and_nothing_is_written(shelf, door, named):
    sold_out("SHA")
    lines_before = OrderLine.objects.count()
    with pytest.raises(Conflict) as refusal:
        NEW_LINE_DOORS[door]({**named, "quantity": "1"})
    assert (refusal.value.code, refusal.value.message) == ("sale.product_sold_out", "«Shampoo» is sold out.")
    assert OrderLine.objects.count() == lines_before
    assert not Sale.objects.exists()
    assert not OutboxEvent.objects.filter(name="sale.sale.completed").exists()


def test_the_refusal_of_a_sold_out_article_is_said_in_spanish(shelf):
    sold_out("SHA")
    with translation.override("es"), pytest.raises(Conflict) as refusal:
        run("sale.checkout.preview", {"lines": [{"product": "SHA"}]}, ctx_for(language="es"))
    assert refusal.value.message == "«Shampoo» está agotado."


def test_a_sold_out_article_in_a_new_check_refuses_the_whole_check(shelf):
    sold_out("SHA")
    with pytest.raises(Conflict) as refusal:
        run("sale.order.open", {"label": "Bar", "lines": [{"product": "WAX"}, {"product": "SHA"}]})
    assert refusal.value.code == "sale.product_sold_out"
    assert not Order.objects.exists()


def test_an_article_back_on_sale_is_sold_again(shelf):
    sold_out("SHA")
    sold_out("SHA", False)
    preview = run("sale.checkout.preview", {"lines": [{"product": "SHA", "quantity": "1"}]})
    assert preview.total == 1200


def test_an_article_that_sells_out_after_ordering_is_still_split_merged_printed_and_charged(shelf):
    """As a menu's dish (COMBO-F08): what was ordered before it sold out is charged; only new lines stop."""
    first = run("sale.order.open", {"label": "Table 4", "lines": [{"product": "SHA"}, {"product": "WAX"}]})
    second = run("sale.order.open", {"label": "Table 5", "lines": [{"product": "SHA"}]})
    sold_out("SHA")
    shampoo = next(line for line in first.lines if line.sku == "SHA")
    split = run("sale.order.split", {"order_id": str(first.id), "line_ids": [str(shampoo.id)]}).new_order
    run("sale.order.merge", {"from_order_id": str(second.id), "to_order_id": str(split.id)})
    run("sale.order.print_bill", {"order_id": str(split.id)})
    assert run("sale.checkout.preview", {"order_id": str(split.id)}).total == 2400
    sale = run(
        "sale.sale.complete",
        {"idempotency_key": "inv-sold-0002", "order_id": str(split.id), "payments": [{"method": "card"}]},
    )
    assert sale.total == 2400
    with pytest.raises(Conflict) as refusal:
        run("sale.order.add_line", {"order_id": str(first.id), "product": "SHA"})
    assert refusal.value.code == "sale.product_sold_out"
