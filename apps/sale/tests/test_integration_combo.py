"""Sale and Menus together, no mocks (SALE-F12; COMBO-F07–F11, «Contrato con Ventas»).

A menu line is priced and checked by Menus' own operation (``combo.combo.resolve``, by name and with the
seller's session) when it is ordered, frozen on the line (its amount, its dishes and how its VAT goes) and
charged with Menus' split: eaten in, ONE line at the menu's VAT; to take away with dishes of different
VAT, one line per dish with the amount split by catalogue price (art. 79.Dos LIVA), with no parent line
carrying money. Charging an open check asks Menus again with the amount ordered (a dish sold out since
does not stop it). The sale notice carries each dish times the menus for Inventory, a refund gives each
dish back, and the kitchen receives the menu with its dishes. Menus is no requirement of Sales: without it
a menu line is refused.
"""

from decimal import Decimal

import pytest
from live.context import system_context
from live.errors import Conflict
from live.models import OutboxEvent

from apps.inventory.models import Product
from apps.sale.models import Order, SaleLine
from apps.sale.tests.conftest import A, run

pytestmark = pytest.mark.django_db

#: Taxes' factory catalogue: restaurant food (10 %), a restaurant's beer (10 % at the table, 21 % to take away).
FOOD = "restaurant.food"
ALCOHOL = "restaurant.alcohol"


def setup(name: str, data: dict):
    return run(name, data, system_context(A))


def stock(sku: str) -> Decimal:
    return Product.objects.get(sku=sku).stock


@pytest.fixture
def menu(product):
    """«Menu of the day», 13,50 € eaten in at 10 %: «Starters» (lentils or salad), «Mains» (hake, or
    steak +2,00 €) and an optional «Dessert» (flan); its kitchen name is «MENU»."""
    product("Lentils", "LEN", 500, FOOD, initial_stock="10")
    product("Salad", "SAL", 450, FOOD, initial_stock="10")
    product("Hake", "HAK", 1400, FOOD, initial_stock="10")
    product("Steak", "STK", 1800, FOOD, initial_stock="10")
    product("Flan", "FLA", 400, FOOD, initial_stock="10")
    setup(
        "combo.combo.create",
        {"name": "Menu of the day", "kitchen_name": "MENU", "price": 1350, "tax_category_key": FOOD},
    )
    setup("combo.group.create", {"combo": "Menu of the day", "name": "Starters"})
    setup("combo.group.create", {"combo": "Menu of the day", "name": "Mains"})
    setup("combo.group.create", {"combo": "Menu of the day", "name": "Dessert", "min_choices": 0})
    options = {}
    for group, sku, delta in (
        ("Starters", "LEN", 0),
        ("Starters", "SAL", 0),
        ("Mains", "HAK", 0),
        ("Mains", "STK", 200),
        ("Dessert", "FLA", 0),
    ):
        options[sku] = str(
            setup(
                "combo.option.create",
                {"combo": "Menu of the day", "group": group, "product": sku, "price_delta": delta},
            ).id
        )
    return options


@pytest.fixture
def takeaway(product):
    """«Sandwich and beer» to take away, 6,00 €: a sandwich of 4,50 € (food, 10 %) and a beer of 2,00 €
    that the bar taxes as a restaurant's (10 %) and takes away at the general rate (21 %)."""
    product("Sandwich", "SAN", 450, FOOD, initial_stock="10")
    product("Beer", "BEE", 200, ALCOHOL, initial_stock="10")
    setup("combo.combo.create", {"name": "Sandwich and beer", "price": 600, "supply_kind": "goods"})
    for group, sku in (("Sandwich", "SAN"), ("Drink", "BEE")):
        setup("combo.group.create", {"combo": "Sandwich and beer", "name": group})
        setup("combo.option.create", {"combo": "Sandwich and beer", "group": group, "product": sku})


def choices(*option_ids: str) -> list[dict]:
    return [{"option_id": option_id} for option_id in option_ids]


def open_check() -> str:
    return str(run("sale.order.open", {"label": "Table 4"}).id)


def add_menu(order_id: str, picks: list[dict], combo: str = "Menu of the day", quantity: str = "1"):
    return run(
        "sale.order.add_combo_line",
        {"order_id": order_id, "combo": combo, "choices": picks, "quantity": quantity},
    )


def charge(key: str, **source):
    return run(
        "sale.sale.complete",
        {"idempotency_key": key, "payments": [{"method": "card"}], **source},
    )


def newest(name: str) -> dict:
    return OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id").first().payload


def test_a_menu_freezes_its_amount_and_dishes_and_charges_one_line_at_the_menus_vat(menu):
    order_id = open_check()
    check = add_menu(order_id, choices(menu["LEN"], menu["STK"], menu["FLA"]))
    (line,) = check.lines
    # 13,50 € closed price plus the steak's 2,00 € supplement.
    assert (line.name, line.unit_price, line.line_total, line.quantity) == (
        "Menu of the day",
        1550,
        1550,
        Decimal("1"),
    )
    assert line.combo.kitchen_name == "MENU" and line.combo.split is False
    assert [(dish.group_name, dish.product_name, dish.price_delta) for dish in line.combo.components] == [
        ("Starters", "Lentils", 0),
        ("Mains", "Steak", 200),
        ("Dessert", "Flan", 0),
    ]
    assert line.kitchen_text == "Lentils, Steak, Flan"

    preview = run("sale.checkout.preview", {"order_id": order_id})
    sale = charge("combo-dine-in-0001", order_id=order_id)
    assert preview.total == sale.total == 1550
    (charged,) = sale.lines
    assert (charged.name, charged.tax_rate, charged.line_total) == ("Menu of the day", Decimal("10"), 1550)
    assert charged.combo_name == "Menu of the day" and charged.product_id is None
    assert [dish.product_name for dish in charged.components] == ["Lentils", "Steak", "Flan"]


def test_to_take_away_the_amount_is_split_per_dish_by_catalogue_price_with_no_parent_line(takeaway):
    """sales#152: 6,00 € over a sandwich of 4,50 € (10 %) and a beer of 2,00 € (21 % to take away):
    4,15 € + 1,85 €, each line at its own VAT, and no line of the menu with money."""
    picks = [{"product": "SAN"}, {"product": "BEE"}]
    preview = run("sale.checkout.preview", {"combo_lines": [{"combo": "Sandwich and beer", "choices": picks}]})
    assert [(row.name, row.line_total, row.tax_rate) for row in preview.lines] == [
        ("Sandwich", 415, Decimal("10")),
        ("Beer", 185, Decimal("21")),
    ]
    assert {row.combo_name for row in preview.lines} == {"Sandwich and beer"}

    sale = charge("combo-takeaway-0001", combo_lines=[{"combo": "Sandwich and beer", "choices": picks}])
    assert sale.total == preview.total == 600
    assert [(row.name, row.tax_category_key, row.line_total) for row in sale.lines] == [
        ("Sandwich", FOOD, 415),
        ("Beer", "retail.alcohol", 185),
    ]
    assert {row.combo_name for row in sale.lines} == {"Sandwich and beer"}
    assert {row.parent_line_id for row in sale.lines} == {None}
    for row in SaleLine.objects.filter(sale_id=sale.id):
        assert row.net_amount + row.tax_amount == row.line_total


def test_an_open_check_keeps_the_menu_and_charging_it_later_equals_charging_it_at_once(takeaway):
    """sales#169 and sales#238: open a check with a menu, take it up again and charge it — the same
    lines and money as charging the menu at the counter."""
    picks = [{"product": "SAN"}, {"product": "BEE"}]
    order_id = str(
        run(
            "sale.order.open",
            {"label": "Ana", "combo_lines": [{"combo": "Sandwich and beer", "choices": picks, "quantity": "2"}]},
        ).id
    )
    again = run("sale.order.get", {"order_id": order_id})
    (line,) = again.lines
    assert (line.name, line.quantity, line.line_total, line.combo.split) == (
        "Sandwich and beer",
        Decimal("2"),
        1200,
        True,
    )

    later = charge("combo-later-0001", order_id=order_id)
    at_once = charge(
        "combo-at-once-0001", combo_lines=[{"combo": "Sandwich and beer", "choices": picks, "quantity": "2"}]
    )
    shape = lambda sale: [  # noqa: E731
        (row.name, row.quantity, row.tax_category_key, row.line_total) for row in sale.lines
    ]
    assert shape(later) == shape(at_once) == [
        ("Sandwich", Decimal("2"), FOOD, 830),
        ("Beer", Decimal("2"), "retail.alcohol", 370),
    ]
    assert later.total == at_once.total == 1200


def test_the_sale_notice_carries_each_dish_times_the_menus_and_inventory_lowers_them(menu):
    """sales#171: the menu has no stock; each dish moves, times the menus sold."""
    sale = charge(
        "combo-stock-0001",
        combo_lines=[
            {"combo": "Menu of the day", "choices": choices(menu["LEN"], menu["HAK"]), "quantity": "2"}
        ],
    )
    (item,) = newest("sale.sale.completed")["items"]
    assert item["product_id"] is None
    assert [(c["product_id"] is not None, c["quantity"], c["is_service"]) for c in item["components"]] == [
        (True, "2.000", False),
        (True, "2.000", False),
    ]

    run("inventory.stock.apply_sale", newest("sale.sale.completed"), system_context(A))
    assert (stock("LEN"), stock("HAK"), stock("SAL")) == (Decimal("8"), Decimal("8"), Decimal("10"))
    assert sale.lines[0].components[0].quantity == 1


def test_refunding_a_menu_gives_each_dish_back(menu):
    """COMBO-F10: a refund sends the dishes of the menus that come back, one line per product."""
    sale = charge(
        "combo-refund-0001",
        combo_lines=[
            {"combo": "Menu of the day", "choices": choices(menu["LEN"], menu["HAK"]), "quantity": "2"}
        ],
    )
    (line,) = sale.lines
    run(
        "sale.sale.refund",
        {
            "sale_id": str(sale.id),
            "reason": "Cold",
            "allocations": [{"payment_id": str(sale.payments[0].id), "amount": 1350}],
            "lines": [{"line_id": str(line.id), "quantity": "1"}],
        },
    )
    returned = newest("sale.sale.refunded")["lines"]
    lentils, hake = Product.objects.get(sku="LEN"), Product.objects.get(sku="HAK")
    assert [(row["product_id"], row["quantity"]) for row in returned] == [
        (str(lentils.id), "1.000"),
        (str(hake.id), "1.000"),
    ]


def test_a_menu_missing_a_required_course_is_refused_and_never_reaches_the_kitchen(menu):
    """sales#535: a half menu does not enter the check, so it can never be fired without its dishes."""
    order_id = open_check()
    with pytest.raises(Conflict) as refused:
        add_menu(order_id, choices(menu["LEN"]))
    assert refused.value.code == "combo.group_incomplete"
    assert run("sale.order.get", {"order_id": order_id}).lines == []
    with pytest.raises(Conflict) as nothing:
        run("sale.order.fire", {"order_id": order_id})
    assert nothing.value.code == "sale.nothing_to_fire"


def test_firing_sends_the_menu_with_its_kitchen_name_and_its_dishes(menu):
    """sales#522: the kitchen learns which dishes the table chose, each with its product and category."""
    order_id = open_check()
    add_menu(order_id, choices(menu["SAL"], menu["HAK"], menu["FLA"]), quantity="2")
    run("sale.order.fire", {"order_id": order_id})
    (item,) = newest("sale.order.fired")["items"]
    assert (item["product_name"], item["kitchen_name"], item["modifiers"]) == (
        "Menu of the day",
        "MENU",
        "Salad, Hake, Flan",
    )
    assert [(dish["product_name"], dish["quantity"]) for dish in item["components"]] == [
        ("Salad", "2.000"),
        ("Hake", "2.000"),
        ("Flan", "2.000"),
    ]
    assert all(dish["product_id"] for dish in item["components"])


def test_a_dish_sold_out_after_ordering_does_not_stop_charging_the_table(menu):
    """COMBO-F08: the open check sends the amount it ordered; availability is not asked again."""
    order_id = open_check()
    add_menu(order_id, choices(menu["LEN"], menu["HAK"], menu["FLA"]))
    setup(
        "combo.option.update",
        {"combo": "Menu of the day", "group": "Dessert", "id": menu["FLA"], "is_available": False},
    )
    with pytest.raises(Conflict) as sold_out:
        add_menu(order_id, choices(menu["LEN"], menu["HAK"], menu["FLA"]))
    assert sold_out.value.code == "combo.option_sold_out"
    sale = charge("combo-sold-out-0001", order_id=order_id)
    assert sale.total == 1350


def test_the_closed_price_ordered_holds_when_the_menu_goes_up(menu):
    order_id = open_check()
    add_menu(order_id, choices(menu["LEN"], menu["HAK"]))
    setup("combo.combo.update", {"combo": "Menu of the day", "price": 1500})
    assert charge("combo-price-0001", order_id=order_id).total == 1350


def test_a_menu_is_sold_in_whole_units_and_its_quantity_can_change(menu):
    order_id = open_check()
    with pytest.raises(Conflict) as half:
        add_menu(order_id, choices(menu["LEN"], menu["HAK"]), quantity="1.5")
    assert half.value.code == "sale.quantity_off_grid"
    (line,) = add_menu(order_id, choices(menu["LEN"], menu["HAK"])).lines
    check = run("sale.order.update_line", {"order_id": order_id, "line_id": str(line.id), "quantity": "3"})
    assert (check.lines[0].quantity, check.lines[0].line_total, check.provisional_total) == (
        Decimal("3"),
        4050,
        4050,
    )


def test_without_menus_a_menu_line_is_refused_and_the_check_stays_as_it_was(menu, monkeypatch):
    order_id = open_check()
    monkeypatch.setattr("apps.sale.queries.COMBO_RESOLVE", "combo.combo.not_installed")
    with pytest.raises(Conflict) as refused:
        add_menu(order_id, choices(menu["LEN"], menu["HAK"]))
    assert refused.value.code == "sale.combo_unavailable"
    assert Order.objects.get(pk=order_id).lines.count() == 0


def test_charging_a_check_splits_the_menu_as_menus_says_today(takeaway):
    """COMBO-F08: charging asks Menus again with the amount ordered; the ticket follows its answer today
    (here the menu became an eaten-in one at 10 %: one line), the money stays the amount ordered."""
    order_id = str(
        run(
            "sale.order.open",
            {"combo_lines": [{"combo": "Sandwich and beer", "choices": [{"product": "SAN"}, {"product": "BEE"}]}]},
        ).id
    )
    setup(
        "combo.combo.update",
        {"combo": "Sandwich and beer", "supply_kind": "service", "tax_category_key": FOOD, "price": 700},
    )
    sale = charge("combo-today-0001", order_id=order_id)
    assert [(row.name, row.tax_category_key, row.line_total) for row in sale.lines] == [
        ("Sandwich and beer", FOOD, 600)
    ]


def test_a_menu_on_the_house_is_on_the_house_in_every_dish(takeaway):
    order_id = str(
        run(
            "sale.order.open",
            {"combo_lines": [{"combo": "Sandwich and beer", "choices": [{"product": "SAN"}, {"product": "BEE"}]}]},
        ).id
    )
    (line,) = run("sale.order.get", {"order_id": order_id}).lines
    run(
        "sale.order.update_line",
        {"order_id": order_id, "line_id": str(line.id), "is_gift": True, "gift_reason": "Birthday"},
    )
    sale = charge("combo-gift-0001", order_id=order_id)
    assert sale.total == 0
    assert [(row.name, row.is_gift, row.line_total) for row in sale.lines] == [
        ("Sandwich", True, 0),
        ("Beer", True, 0),
    ]


def test_a_menu_withdrawn_after_ordering_is_charged_as_it_was_ordered(takeaway):
    """A menu deleted in Menus after a table ordered it («tickets already issued keep their copy», COMBO's
    delete): the check still charges, with the split and the dishes frozen when it was ordered."""
    order_id = str(
        run(
            "sale.order.open",
            {"combo_lines": [{"combo": "Sandwich and beer", "choices": [{"product": "SAN"}, {"product": "BEE"}]}]},
        ).id
    )
    setup("combo.combo.delete", {"combo": "Sandwich and beer"})
    sale = charge("combo-gone-0001", order_id=order_id)
    assert sale.total == 600
    assert [(row.name, row.tax_category_key, row.line_total) for row in sale.lines] == [
        ("Sandwich", FOOD, 415),
        ("Beer", "retail.alcohol", 185),
    ]


def test_with_menus_off_at_the_charge_a_menu_ordered_is_charged_as_it_was_ordered(menu, monkeypatch):
    """Menus switched off after a table ordered a menu: the check still charges what it froze."""
    order_id = open_check()
    add_menu(order_id, choices(menu["LEN"], menu["HAK"]))
    monkeypatch.setattr("apps.sale.queries.COMBO_RESOLVE", "combo.combo.not_installed")
    sale = charge("combo-off-0001", order_id=order_id)
    assert sale.total == 1350
    assert [(row.name, row.tax_category_key, row.line_total) for row in sale.lines] == [("Menu of the day", FOOD, 1350)]
