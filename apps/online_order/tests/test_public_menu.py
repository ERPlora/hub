"""The table's page, which its QR opens without a session (``/p/<slug>/order/<code>``): the business's menu with the
table and its zone above it, read through base's public door holding ``online_order.public`` and nothing else.

The menu is what the till sells and the business shows on its menu: the products on sale by category, each with its
photo, description, price and allergens; what is sold out is left out. A dish's options are its modifier groups, read
when the customer opens it, and the set menus come with their courses and their dishes' allergens. A code that is not a
table's (regenerated, of a deleted table or of another business) reads nothing, and the page never says what is
internal to the business: costs, stock, taxes or its staff.
"""

import pytest
from live.errors import NotFound
from live.operations import Operation, registry

from apps.combo.tests.conftest import make_combo, make_group, make_option, make_product
from apps.modifier.tests.conftest import group as modifier_group
from apps.modifier.tests.conftest import link as modifier_link
from apps.modifier.tests.conftest import option as modifier_option
from apps.online_order import queries
from base.tenancy.context import use_hub
from base.tests.test_public_door import B_HOST, door, turn_off

from .conftest import HOST, HUB_DB, PUBLIC, A, B, make_table, make_zone, regenerate, run, visitor

pytestmark = [HUB_DB, pytest.mark.usefixtures("spa_manifest", "hub_a", "hub_b")]

#: All a dish of the menu tells the customer.
ITEM_FIELDS = {"id", "name", "description", "price", "image_url", "allergens"}


def menu(code: str):
    return run("online_order.public.menu", {"code": code}, visitor())


def options(code: str, product) -> list:
    return run("online_order.public.options", {"code": code, "product_id": str(product.id)}, visitor()).groups


def test_a_table_s_code_opens_the_menu_by_category_with_the_table_and_its_zone(table_code, dishes):
    read = menu(table_code)
    assert (read.table_number, read.zone_name) == ("4", "Terrace")
    assert [(group.name, [item.name for item in group.items]) for group in read.groups] == [
        ("Starters", ["Croquettes"]),
        ("Drinks", ["Cola"]),
    ]
    croquettes = read.groups[0].items[0]
    assert croquettes.model_dump() == {
        "id": dishes["croquettes"].id,
        "name": "Croquettes",
        "description": "Six, of ham",
        "price": 750,
        "image_url": "",
        "allergens": ["gluten", "milk"],
    }


def test_a_regenerated_or_unknown_code_reads_nothing(dishes):
    table = make_table("7")
    old = regenerate(table)
    new = regenerate(table)
    assert menu(new).table_number == "7"
    for code in (old, "not-a-code"):
        with pytest.raises(NotFound) as refused:
            menu(code)
        assert refused.value.code == "online_order.qr_not_active"
        with pytest.raises(NotFound) as refused:
            options(code, dishes["croquettes"])
        assert refused.value.code == "online_order.qr_not_active"


def test_the_code_of_a_deleted_table_reads_nothing(table_code):
    table_id = run("online_order.qr_code.list", {}).rows[0].table_id
    run("table.table.delete", {"id": str(table_id)})
    with pytest.raises(NotFound) as refused:
        menu(table_code)
    assert refused.value.code == "online_order.qr_not_active"


def test_without_dishes_on_the_menu_the_page_has_no_groups(table_code):
    make_product("Staff meal", price=500, sku="STAFF", show_on_website=False)
    read = menu(table_code)
    assert (read.groups, read.combos, read.table_number) == ([], [], "4")


def test_a_set_menu_comes_with_its_courses_and_each_dish_s_allergens(table_code):
    combo = make_combo("Menu of the day", price=1350, kitchen_name="MENU")
    starters, mains = make_group(combo, "Starters"), make_group(combo, "Mains")
    # A dish the menu offers but the business does not show on its own: its allergens still come with it.
    make_option(starters, make_product("Lentils", price=700, sku="LEN", show_on_website=False, allergens=["celery"]))
    make_option(starters, make_product("Soup", price=600, sku="SOU", is_sold_out=True))
    make_option(mains, make_product("Hake", price=1400, sku="HAK", allergens=["fish"]), price_delta=200)
    [read] = menu(table_code).combos
    assert read.model_dump() == {
        "id": combo.id,
        "name": "Menu of the day",
        "price": 1350,
        "image_url": "",
        "courses": [
            {
                "name": "Starters",
                "min_choices": 1,
                "max_choices": 1,
                "choices": [{"name": "Lentils", "price_delta": 0, "allergens": ["celery"]}],
            },
            {
                "name": "Mains",
                "min_choices": 1,
                "max_choices": 1,
                "choices": [{"name": "Hake", "price_delta": 200, "allergens": ["fish"]}],
            },
        ],
    }


def test_past_two_hundred_products_on_sale_no_dish_shown_on_the_menu_is_lost(table_code):
    from apps.inventory.models import Product

    # The kitchen's own, on sale but never shown: more of them than a list's cap.
    Product.objects.bulk_create(
        Product(name=f"Aaa staff {n:03}", sku=f"STAFF{n:03}", price=100, show_on_website=False) for n in range(200)
    )
    zucchini = make_product("Zucchini", price=650, sku="ZUC", allergens=["egg"])
    make_option(make_group(make_combo("Menu of the day"), "Starters"), zucchini)
    read = menu(table_code)
    assert [item.name for group in read.groups for item in group.items] == ["Zucchini"]
    assert [(choice.name, choice.allergens) for choice in read.combos[0].courses[0].choices] == [("Zucchini", ["egg"])]
    assert [group.name for group in options(table_code, zucchini)] == []


def test_with_menus_off_there_are_no_menus(table_code, hub_a):
    make_option(make_group(make_combo("Menu of the day")), make_product("Hake", sku="HAK"))
    turn_off(hub_a, "combo")
    assert menu(table_code).combos == []


def test_a_dish_s_options_are_its_modifier_groups_without_what_the_kitchen_reads(table_code, dishes):
    modifier_group("Sauces", min_choices=0, max_choices=2)
    modifier_option("Sauces", "Aioli", price_delta=50, allergens=["egg"], kitchen_name="AIO")
    modifier_option("Sauces", "Brava")
    modifier_link("Sauces", product_id=str(dishes["croquettes"].id))
    [sauces] = options(table_code, dishes["croquettes"])
    assert sauces.model_dump() == {
        "name": "Sauces",
        "min_choices": 0,
        "max_choices": 2,
        "options": [
            {"name": "Aioli", "price_delta": 50, "allergens": ["egg"]},
            {"name": "Brava", "price_delta": 0, "allergens": []},
        ],
    }
    assert options(table_code, dishes["cola"]) == []


def test_a_dish_off_the_menu_has_no_options_to_read(table_code, dishes):
    for dish in (dishes["staff_meal"], dishes["gone"]):
        with pytest.raises(NotFound) as refused:
            options(table_code, dish)
        assert refused.value.code == "online_order.not_on_menu"


def test_with_modifiers_off_a_dish_has_no_options(table_code, dishes, hub_a):
    modifier_group("Sauces")
    modifier_option("Sauces", "Aioli")
    modifier_link("Sauces", product_id=str(dishes["croquettes"].id))
    turn_off(hub_a, "modifier")
    assert options(table_code, dishes["croquettes"]) == []


# Through the door: what a customer's phone reads.


def keys_of(value) -> set[str]:
    """Every key of a JSON answer, however deep."""
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in keys_of(item)}
    if isinstance(value, list):
        return {key for item in value for key in keys_of(item)}
    return set()


def test_the_phone_reads_the_menu_through_the_door_and_nothing_internal(client, table_code, dishes):
    make_option(make_group(make_combo("Menu of the day", kitchen_name="MENU")), dishes["cola"])
    read = door(client, "online_order.public.menu", {"code": table_code})
    assert read.status_code == 200
    body = read.json()
    assert (body["table_number"], body["zone_name"]) == ("4", "Terrace")
    assert keys_of(body) == {
        "business_name", "table_number", "zone_name", "groups", "combos", "courses", "choices", "min_choices",
        "max_choices", "items", "price_delta", *ITEM_FIELDS,
    }  # fmt: skip
    for internal in ("cost", "sku", "tax", "stock", "kitchen", "staff", "Staff meal", "Gone"):
        assert internal not in read.content.decode()


def test_an_old_code_is_the_404_envelope_without_anything_of_the_business(client, dishes):
    table = make_table("4", make_zone("Terrace"))
    old = regenerate(table)
    regenerate(table)
    refused = door(client, "online_order.public.menu", {"code": old}, HTTP_ACCEPT_LANGUAGE="es")
    assert refused.status_code == 404
    error = refused.json()["error"]
    assert (error["code"], error["message"]) == (
        "online_order.qr_not_active",
        "Este QR ya no está activo; pide ayuda al personal.",
    )
    for told in ("Croquettes", "Terrace", "Cola"):
        assert told not in refused.content.decode()


def test_a_code_of_another_business_reads_nothing_of_either(client, hub_b, dishes):
    with use_hub(hub_b):
        make_product("Paella", price=1500, sku="PAE")
        theirs = regenerate(make_table("9", make_zone("Garden")), B)
    refused = door(client, "online_order.public.menu", {"code": theirs})
    assert (refused.status_code, refused.json()["error"]["code"]) == (404, "online_order.qr_not_active")
    assert "Paella" not in refused.content.decode() and "Garden" not in refused.content.decode()
    other_host = door(client, "online_order.public.menu", {"code": theirs}, host=HOST, slug=B.key)
    assert other_host.status_code == 404
    own = door(client, "online_order.public.menu", {"code": theirs}, host=B_HOST, slug=B.key).json()
    assert ([item["name"] for group in own["groups"] for item in group["items"]], own["zone_name"]) == (
        ["Paella"],
        "Garden",
    )


@pytest.mark.parametrize(
    "operation",
    [
        "online_order.qr_code.list",
        "online_order.qr_code.regenerate",
        "inventory.product.list_for_sale",
        "inventory.product.list",
        "modifier.group.for_target",
        "combo.combo.for_sale",
        "table.table.get",
        "sale.order.open",
        "sale.order.add_line",
        "modifier.selection.resolve",
        "combo.combo.resolve",
    ],
)
def test_the_door_runs_only_the_menu_s_own_reads(client, make_user, table_code, operation):
    # Not even for whoever runs the business: the door holds the page's permission and nothing else.
    client.force_login(make_user("boss", host=A.key, role="hub_owner"))
    refused = door(client, operation, {"code": table_code})
    assert (refused.status_code, refused.json()["error"]["code"]) == (404, "not_found")


def test_the_page_reads_its_table_and_the_menu_and_nothing_else(monkeypatch, table_code, dishes):
    # The door runs only this app's two reads and the order (test_public_send.py); the reads read the other apps with
    # the menu's permissions, and only these.
    assert sorted(op.name for op in registry.values() if op.permission == PUBLIC) == [
        "online_order.public.menu",
        "online_order.public.options",
        "online_order.public.send",
    ]
    assert queries.MENU_READS == {
        "table.view_table",
        "inventory.view_product",
        "inventory.view_category",
        "modifier.view",
        "combo.view",
    }
    called = []
    real = Operation.__call__

    def spy(self, ctx, data):
        called.append((self.name, self.kind))
        return real(self, ctx, data)

    monkeypatch.setattr(Operation, "__call__", spy)
    menu(table_code)
    options(table_code, dishes["croquettes"])
    assert {name for name, _kind in called} == {
        "base.business.get",
        "online_order.public.menu",
        "online_order.public.options",
        "table.table.get",
        "inventory.product.list_for_sale",
        "inventory.category.list",
        "inventory.product_category.list",
        "combo.combo.for_sale",
        "modifier.group.for_target",
    }
    assert {kind for _name, kind in called} == {"query"}


def test_the_page_is_the_shell_for_a_visitor_whatever_the_code(client, table_code):
    for code in (table_code, "not-a-code"):
        opened = client.get(f"/p/{A.key}/order/{code}", HTTP_HOST=HOST)
        assert opened.status_code == 200
        assert "Terrace" not in opened.content.decode()
