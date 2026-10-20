"""Sale and Modifiers together, no mocks (SALE-F11; MODIFIER-F06–F08, «Contrato con Ventas»).

The options chosen for a line are checked and valued by Modifiers' own operation
(``modifier.selection.resolve``, by name and with the seller's session) when the line is added, frozen
on the line, charged with it (or, an option of another tax category, on a child line of its own) and
sent to the kitchen with the line. Modifiers is no requirement of Sales: without it a line with options
is refused and one without enters as before.
"""

from decimal import Decimal

import pytest
from live.context import system_context
from live.errors import Conflict
from live.models import OutboxEvent

from apps.inventory import events as inventory_events
from apps.sale.models import OrderLine, SaleLine
from apps.sale.tests.conftest import A, ctx_for, run

pytestmark = pytest.mark.django_db

#: Taxes' factory catalogue: restaurant food (10 %) and the general rate (21 %).
FOOD = "restaurant.food"
GENERIC = "product.generic"


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


@pytest.fixture
def burger(product):
    """A burger of 8,00 € with its «Extras»: cheese (+1,00 €), no onion (free) and a soda that taxes at
    21 % (+2,00 €, a line of its own); and «Doneness», required, one of two."""
    dish = product("Burger", "BUR", 800, FOOD, initial_stock="10")
    setup("modifier.group.create", {"name": "Extras", "max_choices": 4, "allow_repeat": True})
    setup("modifier.group.create", {"name": "Doneness", "min_choices": 1, "max_choices": 1})
    options = {
        "cheese": setup(
            "modifier.option.create",
            {"group": "Extras", "name": "Cheese", "kitchen_name": "+CHEESE", "price_delta": 100},
        ),
        "onion": setup(
            "modifier.option.create",
            {"group": "Extras", "name": "No onion", "kitchen_name": "-ONION", "price_delta": 0},
        ),
        "soda": setup(
            "modifier.option.create",
            {"group": "Extras", "name": "Soda", "price_delta": 200, "tax_category_key": GENERIC},
        ),
        "rare": setup("modifier.option.create", {"group": "Doneness", "name": "Rare"}),
        "done": setup("modifier.option.create", {"group": "Doneness", "name": "Well done"}),
    }
    for group in ("Extras", "Doneness"):
        setup("modifier.link.attach", {"group": group, "product_id": str(dish.id)})
    return dish, {key: str(option.id) for key, option in options.items()}


def open_check() -> str:
    return str(run("sale.order.open", {"label": "Table 4"}).id)


def add(order_id: str, *option_ids: str, quantity: str = "1", **more):
    return run(
        "sale.order.add_line",
        {"order_id": order_id, "product": "BUR", "quantity": quantity, "option_ids": list(option_ids), **more},
    )


def charge(order_id: str, key: str):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "order_id": order_id, "payments": [{"method": "card"}]},
    )


def newest(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first().payload


def test_the_burger_with_cheese_charges_eight_plus_one_and_the_till_says_the_same(burger):
    _, options = burger
    order_id = open_check()
    check = add(order_id, options["cheese"], options["rare"])
    line = check.lines[0]
    assert (line.unit_price, line.line_total) == (900, 900)
    assert [pick.name for pick in line.modifiers] == ["Cheese", "Rare"]
    assert line.kitchen_text == "+CHEESE, Rare"

    preview = run("sale.checkout.preview", {"order_id": order_id})
    sale = charge(order_id, "mod-cheese-0001")
    assert preview.total == sale.total == 900
    (charged,) = sale.lines
    assert (charged.name, charged.unit_price, charged.line_total) == ("Burger", 900, 900)
    assert charged.modifiers == ["Cheese", "Rare"]


def test_an_option_of_another_tax_goes_on_a_child_line_and_each_line_squares(burger):
    _, options = burger
    order_id = open_check()
    check = add(order_id, options["soda"], options["done"], quantity="2")
    line = check.lines[0]
    # The dish line paints what both lines cost: 2 × 8,00 + 2 × 2,00.
    assert (line.unit_price, line.line_total) == (800, 2000)
    assert [(child.name, child.quantity, child.unit_price) for child in line.modifier_lines] == [
        ("Soda", 1, 200)
    ]

    sale = charge(order_id, "mod-soda-0001")
    dish, soda = sale.lines
    assert (dish.name, dish.quantity, dish.tax_rate, dish.line_total) == ("Burger", Decimal("2"), Decimal("10"), 1600)
    assert (soda.name, soda.quantity, soda.tax_rate, soda.line_total) == ("Soda", Decimal("2"), Decimal("21"), 400)
    assert soda.parent_line_id == dish.id and soda.product_id is None
    assert sale.total == 2000
    for row in SaleLine.objects.filter(sale_id=sale.id):
        assert row.net_amount + row.tax_amount == row.line_total
        assert row.order_line_id == line.id
    assert sum(row.base + row.tax for row in sale.breakdown) == 2000


def test_the_same_option_twice_is_one_child_line_of_its_count_by_the_dishes(burger):
    _, options = burger
    order_id = open_check()
    add(order_id, options["soda"], options["soda"], options["rare"], quantity="3")
    sale = charge(order_id, "mod-soda-twice-01")
    assert [(line.name, line.quantity, line.line_total) for line in sale.lines] == [
        ("Burger", Decimal("3"), 2400),
        ("Soda", Decimal("6"), 1200),
    ]


def test_a_required_group_left_empty_is_refused_also_through_the_api(burger):
    order_id = open_check()
    with pytest.raises(Conflict) as refused:
        add(order_id)
    assert refused.value.code == "modifier.choice_below_min"
    assert "option_ids" in refused.value.fields
    assert not OrderLine.objects.filter(order_id=order_id).exists()


def test_an_option_of_another_product_is_refused_and_nothing_enters(burger, product):
    product("Fries", "FRI", 300, FOOD)
    _, options = burger
    order_id = open_check()
    with pytest.raises(Conflict) as refused:
        run(
            "sale.order.add_line",
            {"order_id": order_id, "product": "FRI", "option_ids": [options["cheese"]]},
        )
    assert refused.value.code == "modifier.option_not_offered"
    assert not OrderLine.objects.filter(order_id=order_id).exists()


def test_what_the_line_was_ordered_at_is_what_it_charges_after_the_option_changes(burger):
    _, options = burger
    order_id = open_check()
    add(order_id, options["cheese"], options["rare"])
    setup("modifier.option.update", {"id": options["cheese"], "price_delta": 300})
    setup("modifier.option.delete", {"id": options["rare"]})
    sale = charge(order_id, "mod-frozen-0001")
    assert sale.total == 900 and sale.lines[0].modifiers == ["Cheese", "Rare"]


def test_a_comp_takes_its_options_and_a_line_discount_its_child_lines(burger):
    _, options = burger
    order_id = open_check()
    check = add(order_id, options["cheese"], options["soda"], options["rare"], is_gift=True)
    assert check.lines[0].line_total == 0
    second = add(order_id, options["soda"], options["rare"])
    line_id = str(second.lines[-1].id)
    run("sale.order.set_line_discount", {"order_id": order_id, "line_id": line_id, "discount_percent": "10"})
    sale = charge(order_id, "mod-comp-disc-01")
    # The comp: 0 for the dish and for its soda; the second: 10 % off 8,00 and off 2,00.
    assert [line.line_total for line in sale.lines] == [0, 0, 720, 180]
    assert sale.total == 900


def test_a_counter_sale_and_an_opened_check_check_their_options_too(burger):
    _, options = burger
    with pytest.raises(Conflict) as refused:
        run(
            "sale.sale.complete",
            {"idempotency_key": "mod-counter-01", "lines": [{"product": "BUR"}], "payments": [{"method": "card"}]},
        )
    assert refused.value.code == "modifier.choice_below_min"
    sale = run(
        "sale.sale.complete",
        {
            "idempotency_key": "mod-counter-02",
            "lines": [{"product": "BUR", "option_ids": [options["cheese"], options["done"]]}],
            "payments": [{"method": "card"}],
        },
    )
    assert sale.total == 900
    opened = run(
        "sale.order.open",
        {"lines": [{"product": "BUR", "option_ids": [options["soda"], options["rare"]]}]},
    )
    assert opened.lines[0].line_total == 1000


def test_the_kitchen_reads_the_options_and_inventory_moves_only_the_dish(burger):
    _, options = burger
    order_id = open_check()
    add(order_id, options["cheese"], options["onion"], options["soda"], options["rare"])
    run("sale.order.fire", {"order_id": order_id})
    (item,) = newest("sale.order.fired")["items"]
    assert item["modifiers"] == "+CHEESE, -ONION, Soda, Rare"

    sale = charge(order_id, "mod-stock-0001")
    items = newest("sale.sale.completed")["items"]
    assert [(entry["product_name"], entry["product_id"] is not None) for entry in items] == [
        ("Burger", True),
        ("Soda", False),
    ]
    assert items[0]["modifiers"] == ["Cheese", "No onion", "Rare"]
    result = inventory_events.react(A, "sale.sale.completed", newest("sale.sale.completed"))
    assert result.movements == 1
    assert sale.number


def test_splitting_and_merging_carry_the_frozen_options_without_asking_again(burger):
    _, options = burger
    order_id = open_check()
    line_id = str(add(order_id, options["soda"], options["rare"]).lines[0].id)
    moved = run("sale.order.split", {"order_id": order_id, "line_ids": [line_id]}).new_order
    setup("modifier.option.update", {"id": options["soda"], "price_delta": 900})
    other = open_check()
    run("sale.order.merge", {"from_order_id": str(moved.id), "to_order_id": other})
    sale = charge(other, "mod-split-merge1")
    assert [line.line_total for line in sale.lines] == [800, 200]


def test_without_modifiers_a_line_with_options_is_refused_and_one_without_enters(burger, monkeypatch):
    monkeypatch.setattr("apps.sale.queries.MODIFIER_RESOLVE", "modifier.selection.not_installed")
    _, options = burger
    order_id = open_check()
    with pytest.raises(Conflict) as refused:
        add(order_id, options["cheese"])
    assert refused.value.code == "sale.modifier_unavailable"
    check = add(order_id)
    assert (check.lines[0].unit_price, check.lines[0].modifiers) == (800, [])


def test_an_employee_adds_options_with_her_own_session(burger):
    _, options = burger
    order_id = open_check()
    check = run(
        "sale.order.add_line",
        {"order_id": order_id, "product": "BUR", "option_ids": [options["cheese"], options["rare"]]},
        ctx_for("hub_employee"),
    )
    assert check.lines[0].unit_price == 900
