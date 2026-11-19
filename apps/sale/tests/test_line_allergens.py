"""The allergens of a line of a check (SALE-F40): frozen from its product when it is ordered, as its options are, and,
in a menu, on each dish picked. The live check and the round sent to the kitchen carry them; the ticket, the invoice
and the bill printed for the table do not. Inventory, Menus and Sales together, no mocks.
"""

import pytest
from django.utils import translation
from live.context import system_context
from live.models import OutboxEvent

from apps.sale import paper
from apps.sale.models import OrderLine, SaleLine
from apps.sale.schemas import (
    OrderAddComboLineIn,
    OrderAddLineIn,
    OrderAddOpenLineIn,
    OrderAddServiceLineIn,
    PreviewLineOut,
)
from apps.sale.tests.conftest import HUB_DB, A, B, ctx_for, run
from base.tenancy.context import use_hub

pytestmark = HUB_DB

FOOD = "restaurant.food"
LETTERHEAD = {"name": "Bar Ana SL", "tax_id": "B12345674", "lines": ["Calle Mayor 1"]}


def setup(name: str, data: dict, scope=A):
    return run(name, data, system_context(scope))


@pytest.fixture
def kitchen(product):
    """A burger with gluten, milk and sesame (declared out of order), a salad without allergens and a flan with egg
    and milk; and «Burger menu», a main (the burger) and a dessert (the flan)."""
    burger = product("Burger", "BUR", 1200, FOOD, allergens=["sesame", "milk", "gluten"])
    product("Salad", "SAL", 800, FOOD)
    flan = product("Flan", "FLA", 400, FOOD, allergens=["milk", "egg"])
    setup("combo.combo.create", {"name": "Burger menu", "price": 1400, "tax_category_key": FOOD})
    options = {}
    for group, sku in (("Main", "BUR"), ("Dessert", "FLA")):
        setup("combo.group.create", {"combo": "Burger menu", "name": group})
        options[sku] = str(
            setup("combo.option.create", {"combo": "Burger menu", "group": group, "product": sku}).id
        )
    return {"burger": burger, "flan": flan, "options": options}


def open_check(**more) -> str:
    return str(run("sale.order.open", {"label": "Table 4", **more}).id)


def add(order_id: str, sku: str):
    return run("sale.order.add_line", {"order_id": order_id, "product": sku})


def add_menu(order_id: str, options: dict):
    picks = [{"option_id": options["BUR"]}, {"option_id": options["FLA"]}]
    return run("sale.order.add_combo_line", {"order_id": order_id, "combo": "Burger menu", "choices": picks})


def live_check(order_id: str):
    return run("sale.order.get", {"order_id": order_id})


def fired_items(order_id: str) -> list[dict]:
    run("sale.order.fire", {"order_id": order_id})
    event = OutboxEvent.objects.filter(name="sale.order.fired").order_by("-created_at", "-id").first()
    return event.payload["items"]


def recast(product, allergens: list[str]) -> None:
    """Inventory changes what the product declares, after it was ordered."""
    setup("inventory.product.update", {"id": str(product.id), "allergens": allergens})


def test_a_line_freezes_its_products_allergens_in_the_order_of_the_list(kitchen):
    order_id = open_check()
    add(order_id, "BUR")
    add(order_id, "SAL")
    burger, salad = live_check(order_id).lines
    assert (burger.allergens, salad.allergens) == (["gluten", "milk", "sesame"], [])
    assert list(OrderLine.objects.order_by("position").values_list("allergens", flat=True)) == [
        ["gluten", "milk", "sesame"],
        [],
    ]


def test_a_line_keeps_what_it_froze_when_inventory_changes_the_product(kitchen):
    order_id = open_check()
    add(order_id, "BUR")
    recast(kitchen["burger"], ["egg"])
    (line,) = live_check(order_id).lines
    assert line.allergens == ["gluten", "milk", "sesame"]
    (item,) = fired_items(order_id)
    assert item["allergens"] == ["gluten", "milk", "sesame"]
    # A new line of the same product takes what Inventory says now.
    assert add(order_id, "BUR").lines[-1].allergens == ["egg"]


def test_the_lines_a_check_opens_with_freeze_theirs_too(kitchen):
    order_id = open_check(
        lines=[{"product": "BUR"}],
        combo_lines=[{"combo": "Burger menu", "choices": [{"product": "BUR"}, {"product": "FLA"}]}],
    )
    burger, menu = live_check(order_id).lines
    assert burger.allergens == ["gluten", "milk", "sesame"]
    assert [dish.allergens for dish in menu.combo.components] == [["gluten", "milk", "sesame"], ["egg", "milk"]]


def test_each_dish_of_a_menu_freezes_its_own_products_allergens(kitchen):
    order_id = open_check()
    add_menu(order_id, kitchen["options"])
    recast(kitchen["flan"], [])
    (line,) = live_check(order_id).lines
    # A menu is no product: its allergens are its dishes', each on its own.
    assert line.allergens == []
    assert [(dish.product_name, dish.allergens) for dish in line.combo.components] == [
        ("Burger", ["gluten", "milk", "sesame"]),
        ("Flan", ["egg", "milk"]),
    ]


def test_a_menu_ordered_before_its_dishes_kept_allergens_says_none(kitchen):
    order_id = open_check()
    add_menu(order_id, kitchen["options"])
    line = OrderLine.objects.get()
    line.combo["components"] = [{k: v for k, v in dish.items() if k != "allergens"} for dish in line.combo["components"]]
    line.save(update_fields=["combo"])
    (menu,) = live_check(order_id).lines
    assert [dish.allergens for dish in menu.combo.components] == [[], []]
    (item,) = fired_items(order_id)
    assert [dish["allergens"] for dish in item["components"]] == [[], []]


def test_the_round_sent_to_the_kitchen_carries_each_lines_and_each_dishs_allergens(kitchen):
    order_id = open_check()
    add(order_id, "BUR")
    add(order_id, "SAL")
    add_menu(order_id, kitchen["options"])
    burger, salad, menu = fired_items(order_id)
    assert (burger["allergens"], salad["allergens"], menu["allergens"]) == (["gluten", "milk", "sesame"], [], [])
    assert [(dish["product_name"], dish["allergens"]) for dish in menu["components"]] == [
        ("Burger", ["gluten", "milk", "sesame"]),
        ("Flan", ["egg", "milk"]),
    ]


def test_a_line_split_in_two_keeps_its_allergens_on_both(kitchen):
    order_id = open_check()
    line_id = str(run("sale.order.add_line", {"order_id": order_id, "product": "BUR", "quantity": "2"}).lines[0].id)
    split = run("sale.order.split_line", {"order_id": order_id, "line_id": line_id})
    assert [line.allergens for line in split.order.lines] == [["gluten", "milk", "sesame"]] * 2


def test_neither_the_ticket_nor_the_bill_for_the_table_says_them(kitchen):
    order_id = open_check()
    add(order_id, "BUR")
    add_menu(order_id, kitchen["options"])
    valued = run("sale.checkout.preview", {"order_id": order_id})
    assert "allergens" not in PreviewLineOut.model_fields
    with translation.override("es"):
        bill = paper.bill(valued, label="Table 4", letterhead=LETTERHEAD, decimals=2)
    assert not {"Gluten", "Leche", "Sésamo", "Huevo"} & set(str(bill).replace(",", " ").split())
    charge = run(
        "sale.sale.complete",
        {"idempotency_key": "allergens-ticket", "order_id": order_id, "payments": [{"method": "card"}]},
    )
    sale = run("sale.sale.get", {"sale_id": str(charge.id)})
    assert not any(hasattr(line, "allergens") for line in sale.lines)
    assert all("allergens" not in dish for line in SaleLine.objects.all() for dish in line.components)


def test_a_line_takes_the_allergens_of_its_own_business(kitchen, hub_b):
    # The other business sells a burger by the same code with other allergens.
    with use_hub(hub_b):
        setup("inventory.product.create", {"name": "Burger", "sku": "BUR", "price": 900, "tax_category_key": FOOD, "allergens": ["fish"]}, B)
        other = str(run("sale.order.open", {"lines": [{"product": "BUR"}]}, ctx_for(scope=B)).id)
    order_id = open_check()
    assert add(order_id, "BUR").lines[0].allergens == ["gluten", "milk", "sesame"]
    with use_hub(hub_b):
        assert run("sale.order.get", {"order_id": other}, ctx_for(scope=B)).lines[0].allergens == ["fish"]


@pytest.mark.parametrize("schema", [OrderAddLineIn, OrderAddOpenLineIn, OrderAddServiceLineIn, OrderAddComboLineIn])
def test_adding_a_line_refuses_a_field_it_does_not_know(schema):
    assert schema.model_config["extra"] == "forbid"
