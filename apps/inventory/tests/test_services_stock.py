"""The stock received, counted and written off."""

import uuid
from decimal import Decimal

import pytest
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import get

from apps.inventory import events
from apps.inventory.models import Product, StockMovement
from apps.inventory.schemas.stock import CountIn
from apps.inventory.tests.test_services import (
    clear_outbox,
    configure,
    count,
    create,
    event_names,
    general,
    movements,
    outbox,
    receive,
    refused,
    stock_of,
    write_off,
)

from .conftest import HUB_DB, ctx_with

#: The general tax category every product of these tests takes, created before each test.
__all__ = ["general"]

pytestmark = HUB_DB


# inventory.stock.receive (INVENTORY-F13)


def test_receiving_raises_the_stock_writes_a_reception_and_updates_the_cost():
    coffee = create("Coffee", cost=200, initial_stock="10", low_stock_threshold="5")
    clear_outbox()

    [after] = receive((coffee.id, "4", {"unit_cost": 180}), reference="ALB-7").rows

    assert (after.stock, after.cost) == (Decimal("14"), 180)
    movement = StockMovement.objects.get(movement_type="reception")
    assert (
        movement.qty,
        movement.stock_after,
        movement.unit_cost,
        movement.reference,
        movement.actor,
    ) == (
        Decimal("4"),
        Decimal("14"),
        180,
        "ALB-7",
        "tester",
    )
    assert outbox() == [
        (
            events.STOCK_CHANGED,
            {
                "product_id": str(coffee.id),
                "movement_type": "reception",
                "qty": "4.000",
                "stock_after": "14.000",
            },
        )
    ]


def test_receiving_without_a_cost_keeps_the_cost_it_had():
    coffee = create("Coffee", cost=500)
    receive((coffee.id, "3"))
    assert Product.objects.get().cost == 500
    assert StockMovement.objects.get().unit_cost is None
    receive((coffee.id, "2", {"unit_cost": 700}))
    assert (Product.objects.get().cost, stock_of(coffee.id)) == (700, Decimal("5"))


def test_a_reception_of_several_products_and_the_same_one_twice():
    coffee, tea = create("Coffee"), create("Tea")
    rows = receive((coffee.id, "1"), (tea.id, "2"), (coffee.id, "3")).rows
    assert {row.name: row.stock for row in rows} == {
        "Coffee": Decimal("4"),
        "Tea": Decimal("2"),
    }
    assert movements(coffee.id) == [
        ("reception", Decimal("1"), Decimal("1")),
        ("reception", Decimal("3"), Decimal("4")),
    ]


def test_a_reception_applies_to_an_article_without_stock_control():
    created = create(track_stock=False)
    receive((created.id, "5"))
    assert stock_of(created.id) == Decimal("5")


def test_half_a_kilo_received_is_half_a_kilo():
    gambas = create("Gambas", unit="kg")
    receive((gambas.id, "2.5"))
    receive((gambas.id, "0.5"))
    assert stock_of(gambas.id) == Decimal("3")


@pytest.mark.parametrize("bad", ["missing", "service", "off_grid"])
def test_a_reception_with_a_bad_line_is_refused_whole_saying_which_line(bad):
    coffee = create("Coffee")
    cut = create("Cut", product_type="service")
    bad_line = {
        "missing": (uuid.uuid7(), "1"),
        "service": (cut.id, "1"),
        "off_grid": (coffee.id, "1.5"),
    }[bad]
    clear_outbox()

    with pytest.raises((InvalidPayload, Conflict)) as excinfo:
        receive((coffee.id, "2"), bad_line)

    error = excinfo.value
    expected = {
        "missing": (422, "invalid_field", "items.1.product_id"),
        "service": (409, "inventory.service_has_no_stock", "items.1.product_id"),
        "off_grid": (409, "inventory.off_grid_quantity", "items.1.qty"),
    }[bad]
    assert (error.status, error.code, list(error.fields)) == (
        expected[0],
        expected[1],
        [expected[2]],
    )
    assert (
        stock_of(coffee.id) == 0
        and not StockMovement.objects.exists()
        and outbox() == []
    )


def test_a_reception_that_lifts_a_tracked_article_above_its_threshold_says_it_recovered():
    low = create("Low", "LOW", initial_stock="2", low_stock_threshold="5")
    clear_outbox()

    receive((low.id, "1"), (low.id, "3"), reference="ALB-9")

    assert outbox(events.STOCK_THRESHOLD_CROSSED) == [
        (
            events.STOCK_THRESHOLD_CROSSED,
            {
                "product_id": str(low.id),
                "sku": "LOW",
                "name": "Low",
                "previous_quantity": "2.000",
                "current_quantity": "6.000",
                "low_stock_threshold": "5.000",
                "crossing": "recovered",
                "movement_type": "reception",
                "reference": "ALB-9",
            },
        )
    ]


def test_moving_stock_needs_its_own_permission():
    coffee = create("Coffee", initial_stock="10")
    editor = ctx_with("inventory.view_product", "inventory.change_product")
    refused(
        PermissionDenied,
        lambda: get("inventory.stock.count")(
            editor, CountIn(product_id=coffee.id, stock="5", reason="count")
        ),
    )
    refused(PermissionDenied, lambda: receive((coffee.id, "1"), role="hub_employee"))
    counter = ctx_with("inventory.adjust_stock")
    assert get("inventory.stock.count")(
        counter, CountIn(product_id=coffee.id, stock="5", reason="recount")
    ).stock == Decimal("5")


# inventory.stock.count (INVENTORY-F14)


def test_a_count_is_absolute_and_the_ledger_keeps_the_difference_and_the_reason():
    coffee = create("Coffee", initial_stock="10")
    clear_outbox()

    assert count(coffee.id, "7", "weekly count: shrinkage").stock == Decimal("7")

    movement = StockMovement.objects.get(movement_type="count")
    assert (movement.qty, movement.stock_after, movement.reason) == (
        Decimal("-3"),
        Decimal("7"),
        "weekly count: shrinkage",
    )
    assert outbox() == [
        (
            events.STOCK_CHANGED,
            {
                "product_id": str(coffee.id),
                "movement_type": "count",
                "qty": "-3.000",
                "stock_after": "7.000",
            },
        )
    ]


def test_a_count_without_difference_writes_nothing():
    coffee = create("Coffee", initial_stock="7")
    clear_outbox()
    count(coffee.id, "7", "recount, no change")
    assert movements(coffee.id, "count") == [] and outbox() == []


def test_a_count_applies_to_an_article_without_stock_control_and_never_crosses():
    created = create(track_stock=False, initial_stock="10", low_stock_threshold="5")
    count(created.id, "1")
    assert stock_of(created.id) == Decimal("1")
    assert events.STOCK_THRESHOLD_CROSSED not in event_names()


def test_a_count_crosses_the_threshold_in_either_direction():
    created = create(initial_stock="10", low_stock_threshold="5")
    count(created.id, "3")
    count(created.id, "4")  # still below: silence
    count(created.id, "8")
    crossings = [
        (payload["crossing"], payload["movement_type"])
        for _, payload in outbox(events.STOCK_THRESHOLD_CROSSED)
    ]
    assert crossings == [("below", "count"), ("recovered", "count")]


def test_a_service_is_not_counted_and_an_off_grid_count_is_refused():
    cut = create("Cut", product_type="service")
    error = refused(Conflict, lambda: count(cut.id, "1"))
    assert (error.code, error.message) == (
        "inventory.service_has_no_stock",
        "A service has no stock.",
    )
    coffee = create("Coffee")
    assert (
        refused(Conflict, lambda: count(coffee.id, "1.5")).code
        == "inventory.off_grid_quantity"
    )


def test_counting_a_missing_product_is_not_found():
    error = refused(NotFound, lambda: count(uuid.uuid7(), "1"))
    assert error.message == "This product does not exist in this hub."


# inventory.stock.write_off (INVENTORY-F15)


def test_a_write_off_lowers_the_stock_with_its_reason():
    wine = create("Wine", "WIN", initial_stock="10", low_stock_threshold="9")
    clear_outbox()

    assert write_off(wine.id, "2", "broken bottles").stock == Decimal("8")

    movement = StockMovement.objects.get(movement_type="write_off")
    assert (movement.qty, movement.stock_after, movement.reason) == (
        Decimal("-2"),
        Decimal("8"),
        "broken bottles",
    )
    assert event_names() == [events.STOCK_CHANGED, events.STOCK_THRESHOLD_CROSSED]
    assert outbox(events.STOCK_THRESHOLD_CROSSED)[0][1]["crossing"] == "below"


def test_without_selling_without_stock_a_write_off_beyond_the_balance_is_refused():
    wine = create("Wine", initial_stock="3")
    clear_outbox()
    error = refused(Conflict, lambda: write_off(wine.id, "9"))
    assert (error.code, error.message) == (
        "inventory.insufficient_stock",
        "There is not enough stock to complete the operation.",
    )
    assert (
        stock_of(wine.id) == Decimal("3")
        and movements(wine.id, "write_off") == []
        and outbox() == []
    )


def test_selling_without_stock_lets_the_balance_go_negative():
    configure(allow_sell_without_stock=True)
    wine = create("Wine", initial_stock="5")
    assert write_off(wine.id, "8").stock == Decimal("-3")


@pytest.mark.parametrize("kind", ["untracked", "business_off"])
def test_a_write_off_of_an_article_without_stock_control_is_refused_and_says_why(kind):
    # The screen offers it only to articles that track stock; by the assistant or the API a write-off
    # that would do nothing is not a silent success either.
    if kind == "business_off":
        configure(track_stock=False)
    created = create(initial_stock="5", track_stock=False if kind == "untracked" else None)
    clear_outbox()
    error = refused(Conflict, lambda: write_off(created.id, "1"))
    message = "This article does not track its stock: there is nothing to write off."
    assert (error.code, error.message, error.fields) == ("inventory.stock_not_tracked", message, {"qty": message})
    assert stock_of(created.id) == Decimal("5") and movements(created.id, "write_off") == [] and outbox() == []


def test_a_write_off_of_a_service_is_refused_as_a_service_has_no_stock():
    massage = create(product_type="service")
    clear_outbox()
    error = refused(Conflict, lambda: write_off(massage.id, "1"))
    assert (error.code, error.fields) == ("inventory.service_has_no_stock", {"product_id": "A service has no stock."})
    assert movements(massage.id, "write_off") == [] and outbox() == []


def test_a_write_off_of_half_a_gram_on_a_gram_step_is_refused():
    gambas = create("Gambas", unit="g", initial_stock="10")
    error = refused(Conflict, lambda: write_off(gambas.id, "0.5"))
    assert error.code == "inventory.off_grid_quantity"
    assert stock_of(gambas.id) == Decimal("10")


def test_writing_off_a_missing_product_is_not_found():
    refused(NotFound, lambda: write_off(uuid.uuid7(), "1"))
