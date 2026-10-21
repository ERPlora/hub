"""Modifiers with the real Sales, no mocks (MODIFIER-F06 and F07; «Contrato con Ventas»).

The till asks the groups of a product (``modifier.group.for_target``) and Sales adds the line with the options
chosen there; Modifiers checks and values them (``modifier.selection.resolve``, called by Sales with the seller's
own session) and is the only source of the supplement's price. What Modifiers promises Sales is checked here
through Sales' own operations: a discount lowers the dish and never takes it below zero, a repeated option counts
as many times as it is chosen, an article sold by weight takes no priced option, and the VAT of every supplement
—folded into the dish or on a line of its own— squares to the cent with what Sales charges.

Traps of the old product: hub#1219 (no sale with a supplement could be charged: the till's read of a module that
was no requirement of Sales was thrown away), hub#1121 (the till asked Modifiers on every tap and got a 404 for a
product without groups).
"""

from decimal import Decimal

import pytest
from live.context import OperationContext
from live.errors import Conflict
from live.meta import all_live_app_configs, permissions_for_role

from apps.sale.models import OrderLine, SaleLine

from .conftest import A, FOOD, GENERIC, make_category, make_product, run

pytestmark = pytest.mark.django_db


def ctx(role: str = "hub_admin") -> OperationContext:
    """Owner and admin hold every declared permission; the others, what each app's role gives them."""
    configs = all_live_app_configs()
    if role in ("hub_owner", "hub_admin"):
        permissions = frozenset(p for config in configs for p in config.permissions)
    else:
        permissions = permissions_for_role(configs, role)
    return OperationContext(scope=A, actor=f"{role}-tester", permissions=permissions, language="en")


def sell(name: str, data: dict, role: str = "hub_admin"):
    return run(name, data, ctx=ctx(role))


def option(group: str, name: str, **fields) -> str:
    return str(run("modifier.option.create", {"group": group, "name": name, **fields}).id)


def open_check(role: str = "hub_admin") -> str:
    return str(sell("sale.order.open", {"label": "Table 7"}, role).id)


def add(order_id: str, sku: str, *option_ids: str, quantity: str = "1", role: str = "hub_admin"):
    data = {"order_id": order_id, "product": sku, "quantity": quantity, "option_ids": list(option_ids)}
    return sell("sale.order.add_line", data, role)


def charge(order_id: str, key: str, role: str = "hub_admin"):
    data = {"idempotency_key": key, "order_id": order_id, "payments": [{"method": "card"}]}
    return sell("sale.sale.complete", data, role)


def valued(sku: str, *option_ids: str):
    return run("modifier.selection.resolve", {"product": sku, "option_ids": list(option_ids)})


@pytest.fixture
def burger(db):
    """A burger of 8,00 € at 10 % in «Mains»: «Doneness» (required, one, «Medium» by default) hangs from the
    category; «Extras» (up to three, repeatable: cheese +1,05 €, no meat −0,50 €, a soda at 21 % +2,05 € on a
    line of its own) and «Empty» (no options) from the product."""
    dish = make_product("Burger", "BUR", 800, FOOD)
    mains = make_category("Mains")
    run("inventory.product_category.add", {"product": "BUR", "category": "Mains"})
    run("modifier.group.create", {"name": "Doneness", "min_choices": 1, "max_choices": 1, "sort_order": 1})
    run("modifier.group.create", {"name": "Extras", "max_choices": 3, "allow_repeat": True, "sort_order": 2})
    run("modifier.group.create", {"name": "Empty", "sort_order": 0})
    ids = {
        "rare": option("Doneness", "Rare", sort_order=1),
        "medium": option("Doneness", "Medium", sort_order=2, is_default=True),
        "cheese": option("Extras", "Cheese", kitchen_name="+CHEESE", price_delta=105),
        "no_meat": option("Extras", "No meat", kitchen_name="-MEAT", price_delta=-50),
        "soda": option("Extras", "Soda", price_delta=205, tax_category_key=GENERIC),
    }
    run("modifier.link.attach", {"group": "Doneness", "category_id": str(mains.id)})
    for group in ("Extras", "Empty"):
        run("modifier.link.attach", {"group": group, "product_id": str(dish.id)})
    return dish, ids


# ── MODIFIER-F06: what the till asks is what Sales takes ────────────────────────────────────────


def test_the_till_asks_the_groups_of_the_dish_and_its_category_and_the_line_takes_what_was_chosen(burger):
    _, ids = burger
    asked = run("modifier.group.for_target", {"product": "BUR"})
    # «Empty» has no options: it is not asked. Its category's «Doneness» comes once, by its order.
    assert [(group.name, group.min_choices, group.max_choices) for group in asked.groups] == [
        ("Doneness", 1, 1),
        ("Extras", 0, 3),
    ]
    doneness, extras = asked.groups
    assert [(choice.name, choice.is_default) for choice in doneness.options] == [("Rare", False), ("Medium", True)]
    assert extras.allow_repeat is True
    defaults = [str(choice.id) for group in asked.groups for choice in group.options if choice.is_default]
    assert defaults == [ids["medium"]]

    order_id = open_check()
    # The waiter taps no meat, keeps the default and adds cheese: the line keeps that order, not the catalogue's.
    line = add(order_id, "BUR", ids["no_meat"], ids["medium"], ids["cheese"]).lines[0]
    assert [pick.name for pick in line.modifiers] == ["No meat", "Medium", "Cheese"]
    assert line.kitchen_text == "-MEAT, Medium, +CHEESE"
    assert line.unit_price == 800 + 105 - 50


def test_a_product_without_groups_is_asked_nothing_and_enters_as_it_is(burger):
    make_product("Fries", "FRI", 300, FOOD)
    assert run("modifier.group.for_target", {"product": "FRI"}).groups == []
    line = add(open_check(), "FRI").lines[0]
    assert (line.unit_price, line.modifiers, line.kitchen_text) == (300, [], "")


# ── MODIFIER-F07: the price and the VAT of the supplement ───────────────────────────────────────


def test_a_discount_lowers_the_dish_and_what_the_check_says_is_what_the_card_pays(burger):
    _, ids = burger
    order_id = open_check()
    line = add(order_id, "BUR", ids["rare"], ids["no_meat"]).lines[0]
    assert (line.unit_price, line.line_total) == (750, 750)
    preview = sell("sale.checkout.preview", {"order_id": order_id})
    sale = charge(order_id, "modifier-discount-01")
    assert preview.total == sale.total == valued("BUR", ids["rare"], ids["no_meat"]).folded_delta + 800 == 750


def test_a_discount_that_would_take_the_dish_below_zero_never_enters_and_one_to_zero_does():
    make_product("Side salad", "SAL", 300, FOOD)
    make_product("Bread", "BRE", 500, FOOD)
    run("modifier.group.create", {"name": "Swap"})
    without = option("Swap", "Without the side", price_delta=-500)
    for sku in ("SAL", "BRE"):
        run("modifier.link.attach", {"group": "Swap", "product": sku})
    order_id = open_check()

    with pytest.raises(Conflict) as refused:
        add(order_id, "SAL", without)
    assert refused.value.code == "modifier.price_below_zero"
    assert "option_ids" in refused.value.fields
    assert not OrderLine.objects.filter(order_id=order_id).exists()

    # Down to zero is a price (a dish on the house): it enters, and a line never goes negative.
    line = add(order_id, "BRE", without).lines[0]
    assert (line.unit_price, line.line_total) == (0, 0)


def test_a_repeated_option_counts_as_many_times_as_it_is_chosen_and_by_every_dish(burger):
    _, ids = burger
    order_id = open_check()
    line = add(order_id, "BUR", ids["rare"], ids["cheese"], ids["cheese"], quantity="3").lines[0]
    assert [pick.name for pick in line.modifiers] == ["Rare", "Cheese", "Cheese"]
    assert (line.unit_price, line.line_total) == (800 + 2 * 105, 3 * (800 + 2 * 105))
    assert charge(order_id, "modifier-repeat-01").total == 3030


def test_the_vat_of_each_supplement_squares_to_the_cent_with_what_sales_charges(burger):
    """Cheese folds into the burger and pays its 10 %; the soda goes on a line of its own at 21 %. Three
    burgers, each with cheese and a soda: 3 × 9,05 € = 27,15 € at 10 % (base 24,68 €, VAT 2,47 €) and
    3 × 2,05 € = 6,15 € at 21 % (base 5,08 €, VAT 1,07 €), rounded half up line by line."""
    _, ids = burger
    picks = valued("BUR", ids["rare"], ids["cheese"], ids["soda"])
    assert (picks.folded_delta, [(own.name, own.price_delta, own.quantity) for own in picks.own_lines]) == (
        105,
        [("Soda", 205, 1)],
    )
    order_id = open_check()
    add(order_id, "BUR", ids["rare"], ids["cheese"], ids["soda"], quantity="3")

    sale = charge(order_id, "modifier-vat-0001")

    rows = {row.name: row for row in SaleLine.objects.filter(sale_id=sale.id)}
    burger_row, soda_row = rows["Burger"], rows["Soda"]
    assert (burger_row.quantity, burger_row.unit_price, burger_row.tax_rate) == (Decimal("3"), 905, Decimal("10"))
    assert (burger_row.line_total, burger_row.net_amount, burger_row.tax_amount) == (2715, 2468, 247)
    assert (soda_row.quantity, soda_row.unit_price, soda_row.tax_rate) == (Decimal("3"), 205, Decimal("21"))
    assert (soda_row.line_total, soda_row.net_amount, soda_row.tax_amount) == (615, 508, 107)
    assert soda_row.parent_line_id == burger_row.id and soda_row.product_id is None
    assert sale.total == 2715 + 615 == 3 * (800 + picks.folded_delta + picks.own_lines[0].price_delta)
    assert sorted((row.rate_pct, row.base, row.tax) for row in sale.breakdown) == [
        (Decimal("10"), 2468, 247),
        (Decimal("21"), 508, 107),
    ]


def test_a_dish_sold_by_weight_takes_a_free_option_but_never_a_priced_one():
    make_product("Ham", "HAM", 4000, FOOD, unit="kg", pricing_unit="kg")
    run("modifier.group.create", {"name": "Cut"})
    sliced = option("Cut", "Sliced")
    fine = option("Cut", "Extra fine", price_delta=100)
    run("modifier.link.attach", {"group": "Cut", "product": "HAM"})
    order_id = open_check()

    with pytest.raises(Conflict) as refused:
        add(order_id, "HAM", fine, quantity="0.350")
    assert refused.value.code == "modifier.priced_by_measure"
    assert not OrderLine.objects.filter(order_id=order_id).exists()

    line = add(order_id, "HAM", sliced, quantity="0.350").lines[0]
    assert (line.unit_price, line.line_total, [pick.name for pick in line.modifiers]) == (4000, 1400, ["Sliced"])


def test_an_employee_charges_a_check_with_supplements_with_her_own_session(burger):
    """hub#1219: Sales does not require Modifiers, yet the cashier's own session reads and values the options."""
    _, ids = burger
    asked = sell("modifier.group.for_target", {"product": "BUR"}, "hub_employee")
    assert [group.name for group in asked.groups] == ["Doneness", "Extras"]
    order_id = open_check("hub_employee")
    add(order_id, "BUR", ids["rare"], ids["cheese"], ids["soda"], role="hub_employee")
    sale = charge(order_id, "modifier-employee-1", role="hub_employee")
    assert [(line.name, line.line_total) for line in sale.lines] == [("Burger", 905), ("Soda", 205)]
