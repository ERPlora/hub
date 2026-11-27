"""What of Menus and combos travels in an export of the business, a backup or a template (BASE-F35): every menu with its
closed price, its courses, the products to choose in each with their supplement, and its own photo, read with the app's
own reads and written with its own creates, so that loading the file brings the menus back as they were.

Every test runs against the real apps (Menus and combos, Inventory, Taxes), in business A's own database, as production
does.
"""

import base64

import pytest

from apps.combo.tests.conftest import FOOD, HUB_DB, in_business_a
from base import blueprint
from base.tenancy.context import use_hub
from base.tenancy.tests.business import A, B
from base.tests.blueprint_round_trip import app_report, call, data_of, exported, loaded_back, owner_of
from base.tests.test_image_catalog import webp
from base.tests.test_images import hub_files

__all__ = ["hub_files", "in_business_a"]
pytestmark = HUB_DB

APPS = ["inventory", "combo"]


@pytest.fixture
def ctx():
    return owner_of(A, "olga")


def a_menu(ctx):
    """The menu of the day, a starter and a main to choose from, and a take-away offer off the till."""
    for name, sku in (("Gazpacho", "GAZ"), ("Steak", "STK"), ("Hake", "HAK")):
        call(ctx, "inventory.product.create", name=name, sku=sku, price=900, tax_category_key=FOOD)
    menu = call(ctx, "combo.combo.create", name="Menu of the day", kitchen_name="MENU", price=1450,
                supply_kind="service", tax_category_key=FOOD, sort_order=1)
    call(ctx, "combo.group.create", combo_id=menu.id, name="Starter")
    call(ctx, "combo.group.create", combo_id=menu.id, name="Main", min_choices=1, max_choices=2, allow_repeat=True)
    call(ctx, "combo.option.create", combo_id=menu.id, group="Starter", product="GAZ")
    call(ctx, "combo.option.create", combo_id=menu.id, group="Main", product="STK", price_delta=300, is_available=False)
    call(ctx, "combo.option.create", combo_id=menu.id, group="Main", product="HAK")
    call(ctx, "combo.combo.create", name="Sandwich and drink", price=650, supply_kind="goods", is_active=False, sort_order=2)
    return menu


def the_menus(ctx) -> dict:
    """Every menu as the business reads it: its fields, and each course with its choices, without ids or dates."""
    menus = {}
    for row in call(ctx, "combo.combo.list", limit=100).rows:
        detail = call(ctx, "combo.combo.get", id=row.id)
        menus[row.name] = (
            (row.kitchen_name, row.price, row.supply_kind, row.tax_category_key, row.sort_order, row.is_active),
            [
                (group.name, group.min_choices, group.max_choices, group.allow_repeat,
                 [(option.sku, option.price_delta, option.is_available) for option in group.options])
                for group in detail.groups
            ],
        )
    return menus


def retire_all(ctx):
    for row in call(ctx, "combo.combo.list", limit=100).rows:
        call(ctx, "combo.combo.delete", id=row.id)


def test_a_backup_brings_the_menus_back_with_their_courses_and_choices(ctx):
    a_menu(ctx)
    before = the_menus(ctx)
    file = exported(ctx, APPS)
    retire_all(ctx)

    report = loaded_back(ctx, file)

    assert the_menus(ctx) == before
    assert [(part["key"], part["created"]) for part in app_report(report, "combo")["datasets"]] == [("combo.combo", 2)]


def test_the_file_carries_each_course_with_its_products_by_their_code(ctx):
    a_menu(ctx)

    menu, offer = data_of(ctx, APPS)["combo.combo"]

    assert (menu["name"], menu["price"], menu["tax_category_key"], menu["is_active"]) == ("Menu of the day", 1450, FOOD, True)
    assert [(course["name"], [choice["product"] for choice in course["choices"]]) for course in menu["courses"]] == [
        ("Starter", ["GAZ"]),
        ("Main", ["STK", "HAK"]),
    ]
    assert (offer["name"], offer["is_active"], offer["courses"]) == ("Sandwich and drink", False, [])


def test_the_menu_s_own_photo_travels_inside_the_file_and_comes_back(ctx, hub_files):
    menu = a_menu(ctx)
    call(ctx, "combo.combo.upload_image", id=menu.id, data_base64=base64.b64encode(webp()).decode("ascii"))
    file = exported(ctx, APPS)
    assert any(name.startswith("combo/") for name in blueprint.archive.read_base64(file).media)
    retire_all(ctx)

    report = loaded_back(ctx, file)

    [back] = [row for row in call(ctx, "combo.combo.list", limit=100).rows if row.name == "Menu of the day"]
    assert back.image.startswith("file:")
    assert app_report(report, "combo")["datasets"][0]["problems"] == []


def test_loading_the_backup_again_duplicates_nothing_and_says_it_was_already_there(ctx):
    a_menu(ctx)
    before = the_menus(ctx)

    report = loaded_back(ctx, exported(ctx, APPS))

    assert the_menus(ctx) == before
    [menus] = app_report(report, "combo")["datasets"]
    assert (menus["status"], menus["already"], menus["created"]) == ("already", 2, 0)


def test_a_choice_whose_product_is_not_in_the_business_is_left_out_and_said(ctx):
    a_menu(ctx)
    bundle = blueprint.archive.read_base64(exported(ctx, ["combo"]))
    retire_all(ctx)
    call(ctx, "inventory.product.delete", id=next(row.id for row in call(ctx, "inventory.product.list", limit=100).rows
                                                  if row.sku == "HAK"))

    result = blueprint.loading.apply(ctx, bundle, apps=None)

    main = the_menus(ctx)["Menu of the day"][1][1]
    assert main[4] == [("STK", 300, False)]
    [menus] = app_report(result.report, "combo")["datasets"]
    assert menus["status"] == "partial"
    assert any("HAK" in problem for problem in menus["problems"])


def test_undoing_the_load_removes_the_menus_it_made(ctx):
    a_menu(ctx)
    bundle = blueprint.archive.read_base64(exported(ctx, ["combo"]))
    retire_all(ctx)
    result = blueprint.loading.apply(ctx, bundle, apps=None)
    assert len(result.created["combo.combo"]) == 2

    blueprint.removal.undo(ctx, result.created)

    assert the_menus(ctx) == {}


def test_settings_data_lists_the_menus_as_what_menus_and_combos_lets_travel(ctx):
    a_menu(ctx)

    apps = {app.id: app for app in call(ctx, "base.dataset.list").apps}

    [menus] = apps["combo"].datasets
    assert (menus.key, menus.label, menus.rows, menus.personal) == ("combo.combo", "Menus", 2, False)


def test_a_backup_of_business_b_carries_its_menus_and_none_of_business_a_s(ctx, hub_b):
    a_menu(ctx)
    with use_hub(hub_b):
        theirs = owner_of(B, "bea")
        call(theirs, "combo.combo.create", name="Brunch", price=1200, supply_kind="goods")

        data = data_of(theirs, ["combo"])

    assert [menu["name"] for menu in data["combo.combo"]] == ["Brunch"]
