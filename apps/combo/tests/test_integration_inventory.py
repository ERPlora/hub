"""Menus with the real Inventory app: its products are the choices, and its stock moves per dish.

Inventory's own operations create, deactivate and delete the products; the event Inventory records when
one is deleted is handed to ``events.react`` as the outbox relay will, from the outbox itself. The sale
notice is built from ``combo.combo.resolve`` exactly as the WORKBOOK's «Contrato con Inventario» asks
Ventas to (COMBO-F10, INVENTORY-F22): the menu moves nothing, each component moves its product.
"""

import uuid
from decimal import Decimal

import pytest
from live.errors import Conflict
from live.live_registry import live_registry
from live.models import OutboxEvent

from apps.combo import events
from apps.combo.models import ChoiceOption
from apps.inventory.models import Product, StockMovement

from .conftest import A, FOOD, ctx_for, run

pytestmark = pytest.mark.django_db


def product(
    name: str, sku: str, *, price: int = 500, stock: str = "10", **fields
) -> Product:
    created = run(
        "inventory.product.create",
        {
            "name": name,
            "sku": sku,
            "price": price,
            "tax_category_key": FOOD,
            "initial_stock": stock,
            **fields,
        },
    )
    return Product.objects.get(pk=created.id)


def menu_of_the_day():
    """Starters: lentils; Mains: hake; Drink: water (no stock control) or a service product."""
    lentils = product("Lentils", "LEN")
    hake = product("Hake", "HAK", price=1400)
    water = product("Water", "WAT", price=200, track_stock=False)
    run(
        "combo.combo.create",
        {"name": "Menu of the day", "price": 1350, "tax_category_key": FOOD},
    )
    for course in ("Starters", "Mains", "Drink"):
        run("combo.group.create", {"combo": "Menu of the day", "name": course})
    for course, sku in (("Starters", "LEN"), ("Mains", "HAK"), ("Drink", "WAT")):
        run(
            "combo.option.create",
            {"combo": "Menu of the day", "group": course, "product": sku},
        )
    return lentils, hake, water


def sale_notice(line, quantity: int) -> dict:
    """The line of `sale.sale.completed` Ventas sends for ``quantity`` menus (WORKBOOK «Contrato con Inventario»)."""
    return {
        "product_id": None,
        "quantity": str(quantity),
        "components": [
            {
                "product_id": str(c.product_id),
                "quantity": str(c.quantity * quantity),
                "is_service": c.is_service,
            }
            for c in line.components
        ],
    }


def stock(item: Product) -> Decimal:
    item.refresh_from_db()
    return item.stock


def test_three_menus_lower_three_portions_of_each_dish_and_never_the_menu():
    lentils, hake, water = menu_of_the_day()
    line = run(
        "combo.combo.resolve",
        {
            "combo": "Menu of the day",
            "choices": [{"product": "LEN"}, {"product": "HAK"}, {"product": "WAT"}],
        },
        ctx_for("hub_employee"),
    )
    sale_id = str(uuid.uuid7())
    run(
        "inventory.stock.apply_sale",
        {"sale_id": sale_id, "items": [sale_notice(line, 3)]},
        ctx_for(permissions={"*"}),
    )
    assert (stock(lentils), stock(hake)) == (Decimal("7"), Decimal("7"))
    # Water does not track its stock: nothing moves, and it is not an error.
    assert stock(water) == Decimal("10")
    assert StockMovement.objects.filter(movement_type="sale").count() == 2
    # Voiding the sale gives back exactly what left.
    run(
        "inventory.stock.restore_sale", {"sale_id": sale_id}, ctx_for(permissions={"*"})
    )
    assert (stock(lentils), stock(hake)) == (Decimal("10"), Decimal("10"))


def test_a_service_dish_travels_as_a_service_and_moves_nothing():
    product("Coffee", "COF", price=150, stock="0", product_type="service")
    run(
        "combo.combo.create",
        {"name": "Breakfast", "price": 400, "tax_category_key": FOOD},
    )
    run("combo.group.create", {"combo": "Breakfast", "name": "Coffee"})
    run(
        "combo.option.create",
        {"combo": "Breakfast", "group": "Coffee", "product": "COF"},
    )
    line = run(
        "combo.combo.resolve",
        {"combo": "Breakfast", "choices": [{"product": "Coffee"}]},
    )
    assert line.components[0].is_service is True
    run(
        "inventory.stock.apply_sale",
        {"sale_id": str(uuid.uuid7()), "items": [sale_notice(line, 1)]},
        ctx_for(permissions={"*"}),
    )
    assert StockMovement.objects.filter(movement_type="sale").count() == 0


def test_the_kitchen_category_of_each_dish_is_inventorys_first():
    menu_of_the_day()
    fish = run("inventory.category.create", {"name": "Fish"})
    run(
        "inventory.product_category.add",
        {"product": "HAK", "category_id": str(fish.id)},
    )
    line = run(
        "combo.combo.resolve",
        {
            "combo": "Menu of the day",
            "choices": [{"product": "LEN"}, {"product": "HAK"}, {"product": "WAT"}],
        },
    )
    assert [c.category_id for c in line.components] == [None, fish.id, None]


def test_a_product_deactivated_in_inventory_is_not_offered_until_it_comes_back():
    lentils, hake, water = menu_of_the_day()
    run("inventory.product.update", {"product": "HAK", "is_active": False})
    assert "combo.combo.for_sale" in live_registry.affected(
        ["inventory.product.updated"]
    )
    detail = run("combo.combo.get", {"combo": "Menu of the day"})
    assert detail.groups[1].options[0].status == "product_inactive"
    assert [b.code for b in detail.blockers] == ["combo.group_short"]
    assert run("combo.combo.for_sale", {}).total == 0
    with pytest.raises(Conflict) as caught:
        run(
            "combo.combo.resolve",
            {
                "combo": "Menu of the day",
                "choices": [{"product": "LEN"}, {"product": "HAK"}, {"product": "WAT"}],
            },
        )
    assert caught.value.code == "combo.product_unavailable"
    run("inventory.product.update", {"product": "HAK", "is_active": True})
    assert run("combo.combo.for_sale", {}).total == 1


def test_a_product_sold_out_in_inventory_is_not_offered_until_it_is_back_on_sale():
    # INVENTORY-F29: the «86» of the catalogue reaches every menu that offers it (Toast, Square).
    lentils, hake, water = menu_of_the_day()
    run("inventory.product.set_sold_out", {"product": "HAK", "sold_out": True})
    assert "combo.combo.for_sale" in live_registry.affected(["inventory.product.updated"])
    detail = run("combo.combo.get", {"combo": "Menu of the day"})
    # Its own switch here is still on: the mark is Inventory's, and the editor says so.
    assert (detail.groups[1].options[0].status, detail.groups[1].options[0].is_available) == ("product_sold_out", True)
    # Mains had only the hake: the menu cannot be completed, so the till stops offering it.
    assert [b.code for b in detail.blockers] == ["combo.group_short"]
    assert run("combo.combo.for_sale", {}).total == 0
    choices = [{"product": "LEN"}, {"product": "HAK"}, {"product": "WAT"}]
    with pytest.raises(Conflict) as caught:
        run("combo.combo.resolve", {"combo": "Menu of the day", "choices": choices})
    assert (caught.value.code, caught.value.message) == ("combo.option_sold_out", "“Hake” is sold out.")
    # A check ordered before the mark is still charged: the last hake served does not stop the table paying.
    charged = run("combo.combo.resolve", {"combo": "Menu of the day", "choices": choices, "amount": 1350})
    assert [c.product_id for c in charged.components] == [lentils.id, hake.id, water.id]
    run("inventory.product.set_sold_out", {"product": "HAK", "sold_out": False})
    assert run("combo.combo.for_sale", {}).total == 1


def test_a_sold_out_choice_leaves_the_till_and_the_menu_stays_with_the_others():
    menu_of_the_day()
    product("Salad", "SAL")
    run("combo.option.create", {"combo": "Menu of the day", "group": "Starters", "product": "SAL"})
    run("inventory.product.set_sold_out", {"product": "LEN", "sold_out": True})
    [menu] = run("combo.combo.for_sale", {}).rows
    starters = next(group for group in menu.groups if group.name == "Starters")
    assert [option.product_name for option in starters.options] == ["Salad"]


def test_without_the_relay_a_deleted_products_choice_is_never_sold_and_is_removed_by_hand():
    # Phase 1 has no outbox relay (COMBO-F13): nothing hands Inventory's notice over, so the choice stays
    # in its menu, marked, and neither the till nor a charge takes it until someone removes it.
    lentils, hake, water = menu_of_the_day()
    run("inventory.product.delete", {"product": "HAK"})
    detail = run("combo.combo.get", {"combo": "Menu of the day"})
    assert detail.groups[1].options[0].status == "product_deleted"
    assert [b.code for b in detail.blockers] == ["combo.group_short"]
    assert run("combo.combo.for_sale", {}).total == 0
    with pytest.raises(Conflict) as caught:
        run(
            "combo.combo.resolve",
            {
                "combo": "Menu of the day",
                "choices": [{"product": "LEN"}, {"product": "HAK"}, {"product": "WAT"}],
            },
        )
    assert caught.value.code == "combo.product_unavailable"
    run("combo.option.delete", {"combo": "Menu of the day", "product": "HAK"})
    assert not ChoiceOption.objects.filter(product=hake).exists()


def test_a_product_deleted_in_inventory_leaves_every_menu_through_its_notice():
    lentils, hake, water = menu_of_the_day()
    run("inventory.product.delete", {"product": "HAK"})
    # Before the relay hands the notice over, the choice is already an orphan nobody can sell.
    assert (
        run("combo.combo.get", {"combo": "Menu of the day"}).groups[1].options[0].status
        == "product_deleted"
    )
    notice = OutboxEvent.objects.filter(name="inventory.product.deleted").latest(
        "created_at"
    )
    assert events.react(A, notice.name, notice.payload).dropped == 1
    assert not ChoiceOption.objects.filter(product=hake).exists()
    dropped = (
        OutboxEvent.objects.filter(name="combo.option.deleted")
        .latest("created_at")
        .payload
    )
    assert (dropped["product_id"], dropped["reason"]) == (
        str(hake.id),
        "product_deleted",
    )


def test_a_product_named_ambiguously_is_inventorys_refusal():
    product("Red wine", "RW1")
    product("Red wine reserve", "RW2")
    run(
        "combo.combo.create",
        {"name": "Dinner", "price": 3000, "tax_category_key": FOOD},
    )
    run("combo.group.create", {"combo": "Dinner", "name": "Wine"})
    with pytest.raises(Conflict) as caught:
        run(
            "combo.option.create",
            {"combo": "Dinner", "group": "Wine", "product": "red"},
        )
    assert caught.value.code == "inventory.product_ambiguous"
    # The exact name wins.
    assert (
        run(
            "combo.option.create",
            {"combo": "Dinner", "group": "Wine", "product": "red wine"},
        ).sku
        == "RW1"
    )


def test_a_refunded_menu_puts_its_dishes_back_when_ventas_sends_them_as_lines():
    # INVENTORY-F24 takes the returned lines; Ventas sends a menu's components × the menus returned.
    lentils, hake, water = menu_of_the_day()
    line = run(
        "combo.combo.resolve",
        {"combo": "Menu of the day", "choices": [{"product": "LEN"}, {"product": "HAK"}, {"product": "WAT"}]},
    )
    sale_id = str(uuid.uuid7())
    run("inventory.stock.apply_sale", {"sale_id": sale_id, "items": [sale_notice(line, 3)]}, ctx_for(permissions={"*"}))
    returned = [{"product_id": str(c.product_id), "quantity": str(c.quantity * 1)} for c in line.components]
    run(
        "inventory.stock.restore_refund",
        {"sale_id": sale_id, "refund_id": str(uuid.uuid7()), "reason": "Cold", "lines": returned},
        ctx_for(permissions={"*"}),
    )
    assert (stock(lentils), stock(hake), stock(water)) == (Decimal("8"), Decimal("8"), Decimal("10"))
