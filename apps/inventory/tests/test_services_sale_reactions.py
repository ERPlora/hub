"""The stock's reactions to sales: a completed sale lowers it, and its void or a refund gives it back."""

import uuid
from decimal import Decimal

import pytest
from live.context import system_context
from live.errors import PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.inventory import events
from apps.inventory.models import Product, SaleStock, StockMovement
from apps.inventory.schemas.fields import ProductRefIn
from apps.inventory.schemas.products import ProductIn
from apps.inventory.schemas.sale_reactions import SaleStockOut
from apps.inventory.tests.test_services import (
    clear_outbox,
    configure,
    create,
    crossings,
    event_names,
    general,
    line,
    movements,
    outbox,
    run,
    sell,
    stock_of,
    update,
    void,
)

from .conftest import A, HUB_DB, ctx_for

#: The general tax category every product of these tests takes, created before each test.
__all__ = ["general"]

pytestmark = HUB_DB


# inventory.stock.apply_sale (INVENTORY-F21, F22, F18)


def test_a_completed_sale_lowers_each_line_with_the_sale_as_reference():
    coffee, gambas = (
        create("Coffee", initial_stock="10"),
        create("Gambas", unit="kg", initial_stock="2.5"),
    )
    sale = uuid.uuid7()
    clear_outbox()

    result = sell(sale, line(coffee.id, "3"), line(gambas.id, "0.5"))

    assert result == SaleStockOut(
        sale_id=sale, state="moved", applied=True, movements=2
    )
    assert (stock_of(coffee.id), stock_of(gambas.id)) == (Decimal("7"), Decimal("2"))
    movement = StockMovement.objects.get(product_id=gambas.id, movement_type="sale")
    assert (movement.qty, movement.stock_after, movement.reference, movement.actor) == (
        Decimal("-0.5"),
        Decimal("2"),
        str(sale),
        "system",
    )
    assert event_names() == [events.STOCK_CHANGED, events.STOCK_CHANGED]
    assert SaleStock.objects.get().state == "moved"


def test_the_same_article_on_several_lines_leaves_a_movement_per_line_and_crosses_once():
    coffee = create("Coffee", initial_stock="10", low_stock_threshold="5")
    menu = line(None, "1", components=[{"product_id": coffee.id, "quantity": "2"}])
    clear_outbox()

    sell(uuid.uuid7(), line(coffee.id, "2"), menu, line(coffee.id, "2"))

    assert [qty for _, qty, _ in movements(coffee.id, "sale")] == [
        Decimal("-2"),
        Decimal("-2"),
        Decimal("-2"),
    ]
    [(_, crossing)] = outbox(events.STOCK_THRESHOLD_CROSSED)
    assert (
        crossing["previous_quantity"],
        crossing["current_quantity"],
        crossing["crossing"],
        crossing["movement_type"],
    ) == (
        "10.000",
        "4.000",
        "below",
        "sale",
    )


def test_a_menu_lowers_its_components_and_never_itself():
    first, drink = (
        create("First", initial_stock="10"),
        create("Drink", initial_stock="10"),
    )
    menu_id = uuid.uuid7()  # the combo is not an article of the catalog
    sell(
        uuid.uuid7(),
        {
            "product_id": menu_id,
            "quantity": "3",
            "components": [
                {"product_id": first.id, "quantity": "3"},
                {"product_id": drink.id, "quantity": "3"},
            ],
        },
    )
    assert (stock_of(first.id), stock_of(drink.id)) == (Decimal("7"), Decimal("7"))
    assert StockMovement.objects.filter(movement_type="sale").count() == 2


def test_services_free_price_lines_and_articles_without_stock_control_move_nothing():
    cut = create("Cut", product_type="service")
    loose = create("Napkin", initial_stock="10", track_stock=False)
    drink = create("Drink", initial_stock="10")
    pack = line(
        None,
        "1",
        components=[
            {"product_id": cut.id, "quantity": "1", "is_service": True},
            {"product_id": drink.id, "quantity": "1"},
        ],
    )

    result = sell(
        uuid.uuid7(),
        line(cut.id, "1", is_service=True),
        line(None, "1"),
        line(loose.id, "2"),
        pack,
    )

    assert (result.movements, stock_of(loose.id), stock_of(drink.id)) == (
        1,
        Decimal("10"),
        Decimal("9"),
    )


def test_the_business_does_not_track_but_the_article_opts_in():
    configure(track_stock=False)
    opted_in, inherits = (
        create("In", initial_stock="10", track_stock=True),
        create("Inherits", initial_stock="10"),
    )
    sell(uuid.uuid7(), line(opted_in.id, "2"), line(inherits.id, "2"))
    assert (stock_of(opted_in.id), stock_of(inherits.id)) == (
        Decimal("8"),
        Decimal("10"),
    )


def test_without_selling_without_stock_an_article_that_does_not_reach_lowers_nothing():
    scarce, plenty = (
        create("Scarce", initial_stock="1"),
        create("Plenty", initial_stock="10"),
    )
    result = sell(uuid.uuid7(), line(scarce.id, "2"), line(plenty.id, "2"))
    assert (stock_of(scarce.id), stock_of(plenty.id), result.movements) == (
        Decimal("1"),
        Decimal("8"),
        1,
    )
    assert movements(scarce.id, "sale") == []


def test_selling_without_stock_goes_negative():
    configure(allow_sell_without_stock=True)
    scarce = create("Scarce", initial_stock="1")
    sell(uuid.uuid7(), line(scarce.id, "3"))
    assert stock_of(scarce.id) == Decimal("-2")


def test_a_sale_that_moves_nothing_is_noted_so_that_its_void_restores_nothing():
    created = create("Coffee", initial_stock="8", track_stock=False)
    sale = uuid.uuid7()
    clear_outbox()
    assert sell(sale, line(created.id, "2")) == SaleStockOut(
        sale_id=sale, state="unmoved", applied=True, movements=0
    )
    assert outbox() == []
    assert void(sale).movements == 0 and stock_of(created.id) == Decimal("8")


def test_a_sale_delivered_twice_lowers_once():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(coffee.id, "3"))
    again = sell(sale, line(coffee.id, "3"))
    assert (again.applied, again.state, stock_of(coffee.id)) == (
        False,
        "moved",
        Decimal("7"),
    )


def test_unknown_and_deleted_products_of_a_sale_are_skipped():
    gone = create("Gone", initial_stock="5")
    run("inventory.product.delete", ProductRefIn(id=gone.id))
    result = sell(uuid.uuid7(), line(uuid.uuid7(), "1"), line(gone.id, "1"))
    assert (result.state, stock_of(gone.id)) == ("unmoved", Decimal("5"))


# inventory.stock.restore_sale (INVENTORY-F23)


def test_a_void_restores_exactly_what_the_sale_lowered():
    coffee = create("Coffee", initial_stock="10", low_stock_threshold="8")
    gambas = create("Gambas", unit="kg", initial_stock="10")
    scarce = create("Scarce", initial_stock="1")
    sale = uuid.uuid7()
    sell(
        sale,
        line(coffee.id, "1"),
        line(coffee.id, "2"),
        line(gambas.id, "2.5"),
        line(scarce.id, "5"),
    )
    clear_outbox()

    result = void(sale)

    assert result == SaleStockOut(
        sale_id=sale, state="voided", applied=True, movements=2
    )
    assert (stock_of(coffee.id), stock_of(gambas.id), stock_of(scarce.id)) == (
        Decimal("10"),
        Decimal("10"),
        Decimal("1"),
    )
    assert movements(coffee.id, "void") == [("void", Decimal("3"), Decimal("10"))]
    assert StockMovement.objects.get(
        product_id=gambas.id, movement_type="void"
    ).reference == str(sale)
    assert event_names() == [
        events.STOCK_CHANGED,
        events.STOCK_THRESHOLD_CROSSED,
        events.STOCK_CHANGED,
    ]
    assert outbox(events.STOCK_THRESHOLD_CROSSED)[0][1]["crossing"] == "recovered"


def test_a_void_delivered_twice_restores_once():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(coffee.id, "3"))
    void(sale)
    assert void(sale).applied is False
    assert stock_of(coffee.id) == Decimal("10")


def test_a_void_that_arrives_before_its_sale_leaves_the_stock_as_it_was():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    assert void(sale) == SaleStockOut(
        sale_id=sale, state="voided", applied=True, movements=0
    )
    assert sell(sale, line(coffee.id, "3")).applied is False
    assert stock_of(coffee.id) == Decimal("10") and movements(coffee.id, "sale") == []


def test_a_void_restores_even_if_the_article_stopped_tracking_stock_in_between():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(coffee.id, "4"))
    update(coffee.id, track_stock=False)
    void(sale)
    assert stock_of(coffee.id) == Decimal("10")


def test_an_article_deleted_after_the_sale_gets_nothing_back():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(coffee.id, "4"))
    run("inventory.product.delete", ProductRefIn(id=coffee.id))
    assert void(sale).movements == 0
    assert stock_of(coffee.id) == Decimal("6")


# inventory.stock.restore_refund (INVENTORY-F24)


def refunded(sale_id, *lines, refund_id=None, reason="returned"):
    """What Sales records as ``sale.sale.refunded`` (apps/sale/services/refunds.py ``refund``), whole."""
    payload = {
        "sale_id": str(sale_id),
        "sale_number": "20261014-0001",
        "refund_id": str(refund_id or uuid.uuid7()),
        "total": 100,
        "reason": reason,
        "refunded_by": "tester",
        "refunded_at": "2026-10-14T10:00:00+00:00",
        "fully_refunded": False,
        "document_type": "ticket",
        "order_id": None,
        "customer_id": None,
        "payments": [],
        "lines": [
            {"line_id": str(uuid.uuid7()), "product_id": str(product_id) if product_id else None, "quantity": quantity}
            for product_id, quantity in lines
        ],
    }
    op = get("inventory.stock.restore_refund")
    return op(system_context(A), op.input.model_validate(payload))


def test_restore_refund_is_a_reaction_of_the_platform_without_a_route():
    op = get("inventory.stock.restore_refund")
    assert (op.kind, op.permission, op.expose_api) == ("command", "inventory.system", False)
    assert op.ai["risk"] == "high" and op.ai["description"]
    # Not a permission of any role: the owner holds every permission inventory declares, not this one.
    with pytest.raises(PermissionDenied):
        op(ctx_for("hub_owner"), op.input.model_validate({"sale_id": str(uuid.uuid7()), "refund_id": str(uuid.uuid7())}))


def test_a_refund_puts_back_the_returned_units_of_its_lines_once():
    wine = create("Wine", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(wine.id, "4"))
    clear_outbox()
    refund_id = uuid.uuid7()

    first = refunded(sale, (wine.id, "3.000"), refund_id=refund_id, reason="corked")
    again = refunded(sale, (wine.id, "3.000"), refund_id=refund_id, reason="corked")

    assert (first.applied, first.movements, again.applied, again.movements) == (True, 1, False, 0)
    assert stock_of(wine.id) == Decimal("9")
    assert movements(wine.id, "refund") == [("refund", Decimal("3"), Decimal("9"))]
    movement = StockMovement.objects.get(movement_type="refund")
    assert (movement.reference, movement.reason) == (str(sale), "corked")
    assert event_names() == [events.STOCK_CHANGED]


def test_two_refunds_of_a_sale_never_give_back_more_than_it_took():
    wine = create("Wine", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(wine.id, "4"))
    refunded(sale, (wine.id, "3"))
    assert refunded(sale, (wine.id, "3")).movements == 1
    assert stock_of(wine.id) == Decimal("10")  # 4 out, 4 back: the second refund was capped at 1


def test_a_refund_gives_back_nothing_the_sale_did_not_lower():
    configure(allow_sell_without_stock=False)
    untracked = create("Bag", initial_stock="5", track_stock=False)
    short = create("Rare", initial_stock="1")
    massage = create("Massage", product_type="service")
    sale = uuid.uuid7()
    sell(sale, line(untracked.id, "1"), line(short.id, "2"), line(massage.id, "1"))
    result = refunded(sale, (untracked.id, "1"), (short.id, "2"), (massage.id, "1"), (None, "1"))
    assert (result.applied, result.movements) == (True, 0)
    assert (stock_of(untracked.id), stock_of(short.id)) == (Decimal("5"), Decimal("1"))


def test_a_refund_respects_an_article_that_stopped_tracking_its_stock():
    wine = create("Wine", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(wine.id, "2"))
    update(wine.id, track_stock=False)
    assert refunded(sale, (wine.id, "2")).movements == 0
    assert stock_of(wine.id) == Decimal("8")


def test_a_refund_that_lifts_an_article_over_its_threshold_says_it_recovered():
    wine = create("Wine", initial_stock="6", low_stock_threshold="5")
    sale = uuid.uuid7()
    sell(sale, line(wine.id, "3"))  # 6 → 3: below
    refunded(sale, (wine.id, "3"))  # 3 → 6: recovered
    assert crossings() == [("below", "sale"), ("recovered", "refund")]


def test_a_void_after_a_partial_refund_restores_only_what_is_still_out():
    wine = create("Wine", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(wine.id, "4"))
    refunded(sale, (wine.id, "1"))
    assert void(sale).movements == 1
    assert stock_of(wine.id) == Decimal("10")
    assert movements(wine.id, "void") == [("void", Decimal("3"), Decimal("10"))]


def test_a_refund_of_a_voided_or_unseen_sale_gives_back_nothing():
    wine = create("Wine", initial_stock="10")
    voided = uuid.uuid7()
    sell(voided, line(wine.id, "4"))
    void(voided)
    assert refunded(voided, (wine.id, "4")).movements == 0
    assert refunded(uuid.uuid7(), (wine.id, "4")).movements == 0
    assert stock_of(wine.id) == Decimal("10")


def test_a_money_only_refund_moves_nothing_and_is_noted_once():
    wine = create("Wine", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(wine.id, "1"))
    refund_id = uuid.uuid7()
    assert refunded(sale, refund_id=refund_id).applied is True
    assert refunded(sale, (wine.id, "1"), refund_id=refund_id).applied is False
    assert stock_of(wine.id) == Decimal("9")


def test_the_real_refund_of_sales_reaches_the_stock():
    """With the payload Sales really records (its app is imported here only, in the tests)."""
    from apps.sale.tests.conftest import ctx_for as sale_ctx_for, run as sale_run

    run("inventory.product.create", ProductIn(name="Coffee", sku="COF", price=1210, tax_category_key="product.generic", initial_stock="10"))
    sale = sale_run("sale.sale.complete", {"idempotency_key": "inv-svc-refund-01", "lines": [{"product": "COF", "quantity": "2"}], "payments": [{"method": "card"}]}, sale_ctx_for(scope=A))
    events.react(A, "sale.sale.completed", OutboxEvent.objects.filter(name="sale.sale.completed").latest("created_at").payload)
    sale_run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id), "reason": "a cup back",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 1210}],
            "lines": [{"line_id": str(sale.lines[0].id), "quantity": "1"}],
        },
        sale_ctx_for(scope=A),
    )
    payload = OutboxEvent.objects.filter(name="sale.sale.refunded").latest("created_at").payload
    op = get("inventory.stock.restore_refund")
    result = op(system_context(A), op.input.model_validate(payload))
    assert (str(result.refund_id), str(result.sale_id), result.movements) == (payload["refund_id"], str(sale.id), 1)
    assert Product.objects.get(sku="COF").stock == Decimal("9")
