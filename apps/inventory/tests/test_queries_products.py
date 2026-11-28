"""The products' reads (``apps/inventory/queries/products.py``): the list, the product, the sale catalog and the
low-stock list."""

import uuid
from decimal import Decimal

import pytest
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.inventory.models import Category, Product, Settings
from apps.inventory.schemas.fields import ProductRefIn
from apps.inventory.schemas.products import ForSaleListIn, ProductListIn
from apps.inventory.schemas.stock import LowStockListIn
from apps.tax.models import TaxCategory

from .conftest import HUB_DB, ctx_for, link, names, product, run

pytestmark = HUB_DB


def test_the_sale_catalog_says_each_products_description():
    Product.objects.create(name="Tostada", sku="TOST", price=350, description="Pan de pueblo con tomate.")
    Product.objects.create(name="Agua", sku="AGUA", price=150)

    rows = get("inventory.product.list_for_sale")(ctx_for("hub_admin"), ForSaleListIn()).rows

    assert {row.name: row.description for row in rows} == {"Tostada": "Pan de pueblo con tomate.", "Agua": ""}


# inventory.product.list


def test_empty_list():
    assert run("inventory.product.list", ProductListIn()).model_dump() == {
        "rows": [],
        "total": 0,
        "limit": 50,
        "offset": 0,
    }


def test_a_row_has_everything_the_screen_and_the_form_show(general):
    drinks = Category.objects.create(name="Drinks")
    coffee = product(
        "Coffee",
        "CAF-1",
        tax=general,
        cost=40,
        stock=Decimal("3"),
        ean13="8412345678905",
    )
    link(coffee, drinks)

    [row] = run("inventory.product.list", ProductListIn()).rows

    assert row.model_dump(exclude={"created_at", "updated_at"}) == {
        "id": coffee.id,
        "name": "Coffee",
        "sku": "CAF-1",
        "ean13": "8412345678905",
        "description": "",
        "allergens": [],
        "product_type": "physical",
        "price": 100,
        "cost": 40,
        "stock": Decimal("3.000"),
        "low_stock_threshold": Decimal("10.000"),
        "unit": "ud",
        "price_quantity": Decimal("1.000"),
        "pricing_unit": "ud",
        "tax_category_id": general.id,
        "tax_category_key": "product.general",
        "needs_tax_setup": False,
        "track_stock": None,
        "tracks_stock": True,
        "is_active": True,
        "is_sold_out": False, "show_on_website": True,
        "category_ids": [drinks.id],
        # No image yet, so the till shows its initials.
        "image": "",
        "image_url": "",
    }


def test_deleted_products_are_out_of_every_list():
    product("Gone", is_deleted=True, is_active=False)
    product("Here")
    assert names(run("inventory.product.list", ProductListIn())) == ["Here"]


def test_ordered_by_name_and_paged_stably_with_id_as_tie_break():
    made = [product("Same", f"S-{n}") for n in range(5)]
    expected = sorted(item.id for item in made)
    pages = [
        run("inventory.product.list", ProductListIn(limit=2, offset=offset))
        for offset in (0, 2, 4)
    ]
    assert [row.id for page in pages for row in page.rows] == expected
    assert [page.total for page in pages] == [5, 5, 5]


def test_sorting_by_a_column():
    product("Cheap", price=50)
    product("Dear", price=900)
    product("Mid", price=300)
    assert names(run("inventory.product.list", ProductListIn(sort="-price"))) == [
        "Dear",
        "Mid",
        "Cheap",
    ]
    assert names(run("inventory.product.list", ProductListIn(sort="price"))) == [
        "Cheap",
        "Mid",
        "Dear",
    ]


def test_search_by_name_or_sku_ignoring_case():
    product("Coffee", "CAF-1")
    product("Tea", "TEA-1")
    product("Decaf", "DEC-1")
    assert names(run("inventory.product.list", ProductListIn(search="caf"))) == [
        "Coffee",
        "Decaf",
    ]
    assert names(run("inventory.product.list", ProductListIn(search="tea-1"))) == [
        "Tea"
    ]


def test_filters_narrow_on_the_server(general):
    drinks, food = (
        Category.objects.create(name="Drinks"),
        Category.objects.create(name="Food"),
    )
    coffee = product("Coffee", "CAF", tax=general, price=150, stock=Decimal("8"))
    beer = product(
        "Beer", "BEER", tax=general, price=300, stock=Decimal("2"), is_active=False
    )
    bread = product("Bread", "BRE", price=90, stock=Decimal("20"))
    cut = product("Haircut", "CUT", tax=general, product_type="service", price=2500)
    link(coffee, drinks)
    link(beer, drinks)
    link(bread, food)

    def listed(**filters):
        return names(run("inventory.product.list", ProductListIn(**filters)))

    assert listed(category_id=drinks.id) == ["Beer", "Coffee"]
    assert listed(category_id=uuid.uuid7()) == []
    assert listed(name="ee") == ["Beer", "Coffee"]
    assert listed(sku="BRE") == ["Bread"]
    assert listed(price_min=100, price_max=200) == ["Coffee"]
    assert listed(stock_min=Decimal("5")) == ["Bread", "Coffee"]
    assert listed(stock_max=Decimal("2")) == ["Beer", "Haircut"]
    assert listed(status="active") == ["Coffee", "Haircut"]
    assert listed(status="inactive") == ["Beer"]
    assert listed(status="needs_tax_setup") == ["Bread"]
    assert listed(product_type="service") == ["Haircut"]
    assert cut.id in {
        row.id for row in run("inventory.product.list", ProductListIn()).rows
    }


def test_a_product_without_tax_category_needs_setup():
    product("Bread")
    [row] = run("inventory.product.list", ProductListIn()).rows
    assert (row.needs_tax_setup, row.tax_category_id, row.tax_category_key) == (
        True,
        None,
        None,
    )


def test_what_applies_to_each_article_follows_its_own_decision_or_the_business():
    product("Inherits")
    product("Opted out", track_stock=False)
    product("Opted in", track_stock=True)
    product("Service", product_type="service", track_stock=True)

    def tracking():
        return {
            row.name: row.tracks_stock
            for row in run("inventory.product.list", ProductListIn()).rows
        }

    assert tracking() == {
        "Inherits": True,
        "Opted in": True,
        "Opted out": False,
        "Service": False,
    }
    Settings.objects.create(track_stock=False)
    assert tracking() == {
        "Inherits": False,
        "Opted in": True,
        "Opted out": False,
        "Service": False,
    }


def test_a_deleted_category_is_not_among_the_product_categories():
    coffee = product("Coffee")
    gone = Category.objects.create(name="Gone", is_deleted=True)
    link(coffee, gone)
    assert run("inventory.product.get", ProductRefIn(id=coffee.id)).category_ids == []


def test_an_employee_may_list_and_a_stranger_may_not():
    product("Coffee")
    assert (
        run("inventory.product.list", ProductListIn(), role="hub_employee").total == 1
    )
    with pytest.raises(PermissionDenied):
        run("inventory.product.list", ProductListIn(), role="nobody")


# inventory.product.get


def test_get_a_product():
    coffee = product("Coffee")
    assert (
        run("inventory.product.get", ProductRefIn(id=coffee.id), role="hub_employee").name
        == "Coffee"
    )


def test_get_a_product_by_its_sku_or_name_as_a_person_says_it():
    red = product("Red wine", "WIN-R")
    product("White wine", "WIN-W")
    product("Rosé", "ROS")

    def said(text):
        return run("inventory.product.get", ProductRefIn(product=text)).id

    assert said("win-r") == red.id  # the SKU, ignoring case
    assert said("RED WINE") == red.id  # the exact name
    assert said("red") == red.id  # the only name that contains it
    with pytest.raises(Conflict) as excinfo:
        said("wine")
    assert excinfo.value.code == "inventory.product_ambiguous"
    assert "Red wine (WIN-R)" in excinfo.value.message and "White wine (WIN-W)" in excinfo.value.message
    with pytest.raises(NotFound):
        said("beer")


def test_a_deleted_product_is_not_found_by_its_sku():
    product("Gone", "GONE", is_deleted=True)
    with pytest.raises(NotFound):
        run("inventory.product.get", ProductRefIn(product="GONE"))


@pytest.mark.parametrize("deleted", [True, False])
def test_get_a_missing_or_deleted_product_is_not_found(deleted):
    target = product("Gone", is_deleted=True).id if deleted else uuid.uuid7()
    with pytest.raises(NotFound) as excinfo:
        run("inventory.product.get", ProductRefIn(id=target))
    assert excinfo.value.message == "This product does not exist in this hub."


# inventory.product.list_for_sale


def test_the_sale_catalog_has_only_active_live_products_with_what_prices_them(general):
    coffee = product(
        "Coffee",
        "CAF",
        tax=general,
        price=150,
        cost=40,
        unit="kg",
        pricing_unit="g",
        price_quantity=Decimal("100"),
    )
    product("Off", is_active=False)
    product("Gone", is_deleted=True, is_active=False)
    product("Untaxed")
    product("Cut", product_type="service", tax=general)

    page = run("inventory.product.list_for_sale", ForSaleListIn(), role="hub_manager")

    assert [row.name for row in page.rows] == ["Coffee", "Cut", "Untaxed"]
    assert page.rows[0].model_dump() == {
        "id": coffee.id,
        "name": "Coffee",
        "description": "",
        "sku": "CAF",
        "product_type": "physical",
        "price": 150,
        "cost": 40,
        "tax_category_id": general.id,
        "tax_category_key": "product.general",
        "needs_tax_setup": False,
        "unit": "kg",
        "price_quantity": Decimal("100.000"),
        "pricing_unit": "g",
        "allergens": [], "show_on_website": True,
        "tracks_stock": True,
        # INVENTORY-F32: the till's tile shows it, or its initials without one.
        "image": "", "image_url": "",
    }
    assert [row.tracks_stock for row in page.rows] == [True, False, True]
    assert page.rows[2].needs_tax_setup is True
    # The till neither shows nor checks availability: the sale catalog carries no stock.
    assert "stock" not in page.rows[0].model_dump()


def test_the_sale_catalog_leaves_out_a_sold_out_article(general):
    product("Coffee", tax=general)
    product("Croquettes", tax=general, is_sold_out=True)
    assert names(run("inventory.product.list_for_sale", ForSaleListIn())) == ["Coffee"]


# A sold-out article (INVENTORY-F29) stays in Products and leaves what the till offers (INVENTORY-F27)


def test_a_sold_out_article_stays_in_products_and_leaves_what_the_till_offers(general):
    product("Coffee", tax=general)
    product("Croquettes", tax=general, is_sold_out=True)
    product("Off", tax=general, is_active=False)

    def listed(**filters):
        return names(run("inventory.product.list", ProductListIn(**filters)))

    # The till asks for what is on sale (SALE-F01 reads `is_active: true`): active and not sold out.
    assert listed(is_active=True) == ["Coffee"]
    assert listed(is_active=False) == ["Croquettes", "Off"]
    # Products shows it, its switch still on («Yes») and its mark, and filters by the mark.
    rows = run("inventory.product.list", ProductListIn()).rows
    assert [(row.name, row.is_active, row.is_sold_out) for row in rows] == [
        ("Coffee", True, False),
        ("Croquettes", True, True),
        ("Off", False, False),
    ]
    assert listed(status="active") == ["Coffee", "Croquettes"]
    assert listed(status="sold_out") == ["Croquettes"]
    # A screen that configures rather than sells (a menu's choices, COMBO-F06) still picks a sold-out
    # article: with include_sold_out, is_active is the switch alone.
    assert listed(is_active=True, include_sold_out=True) == ["Coffee", "Croquettes"]
    assert listed(is_active=False, include_sold_out=True) == ["Off"]


def test_the_detail_of_a_sold_out_article_says_so(general):
    croquettes = product("Croquettes", tax=general, is_sold_out=True)
    # What Sales reads by name when it freezes a line (SALE-F01): still the product, marked.
    detail = run("inventory.product.get", ProductRefIn(product="croquettes"), role="hub_employee")
    assert (detail.id, detail.is_active, detail.is_sold_out) == (croquettes.id, True, True)


# inventory.product.list_low_stock


def test_low_stock_lists_tracked_physical_active_articles_at_or_under_their_threshold():
    threshold = {"low_stock_threshold": Decimal("5")}
    product("A", stock=Decimal("10"), **threshold)  # above
    product("B", stock=Decimal("0"), **threshold)  # out
    product("C", stock=Decimal("2"), **threshold)  # under
    product("D", stock=Decimal("-3"), **threshold)  # oversold
    product("E", stock=Decimal("5"), **threshold)  # at
    product("S", stock=Decimal("0"), product_type="service", **threshold)
    product("U", stock=Decimal("0"), track_stock=False, **threshold)
    product("I", stock=Decimal("0"), is_active=False, **threshold)

    page = run(
        "inventory.product.list_low_stock", LowStockListIn(), role="hub_employee"
    )

    # The one with less first.
    assert [(row.name, row.stock) for row in page.rows] == [
        ("D", Decimal("-3.000")),
        ("B", Decimal("0.000")),
        ("C", Decimal("2.000")),
        ("E", Decimal("5.000")),
    ]
    assert list(page.rows[0].model_dump()) == [
        "id", "name", "sku", "stock", "low_stock_threshold", "is_sold_out", "unit", "price_quantity", "pricing_unit",
    ]
    assert names(
        run("inventory.product.list_low_stock", LowStockListIn(search="c"))
    ) == ["C"]


# The old module's filters and orders, all kept (list_filters_narrow_on_the_server, manifest list blocks)


def test_the_product_list_filters_of_the_old_module(general):
    drinks = Category.objects.create(name="Drinks", slug="bebidas")
    coffee = product("Coffee", tax=general)
    product("Bread")
    product("Off", tax=general, is_active=False)
    product("Napkin", tax=general, track_stock=False)
    link(coffee, drinks)

    def listed(**filters):
        return names(run("inventory.product.list", ProductListIn(**filters)))

    assert listed(is_active=False) == ["Off"]
    assert listed(needs_tax_setup=True) == ["Bread"]
    assert listed(needs_tax_setup=False, is_active=True) == ["Coffee", "Napkin"]
    assert listed(tracks_stock=False) == ["Napkin"]
    assert listed(category="Drinks") == ["Coffee"]
    assert listed(category="BEBIDAS") == ["Coffee"]
    assert listed(category="nothing") == []


def test_low_stock_filters_and_orders():
    threshold = {"low_stock_threshold": Decimal("5")}
    product("Bravo", "B-2", stock=Decimal("1"), **threshold)
    product("Alpha", "A-1", stock=Decimal("4"), **threshold)
    product("Charlie", "C-3", stock=Decimal("0"), low_stock_threshold=Decimal("9"))

    def listed(**params):
        return names(run("inventory.product.list_low_stock", LowStockListIn(**params)))

    assert listed() == ["Charlie", "Bravo", "Alpha"]
    assert listed(sort="name") == ["Alpha", "Bravo", "Charlie"]
    assert listed(sort="-low_stock_threshold") == ["Charlie", "Alpha", "Bravo"]
    assert listed(sku="B-2") == ["Bravo"]
    assert listed(sku="B") == []  # the SKU is exact
    assert listed(stock_min=Decimal("1"), stock_max=Decimal("3")) == ["Bravo"]


def test_a_product_whose_tax_category_was_deactivated_needs_setup_again():
    # INVENTORY-F05: «the products whose tax category is no longer in Taxes»; none is invented.
    old = TaxCategory.objects.create(key="test.old", name="Old", is_active=False)
    product("Bread", tax=old)
    [row] = run("inventory.product.list", ProductListIn()).rows
    assert (row.needs_tax_setup, row.tax_category_key) == (True, "test.old")
    assert names(run("inventory.product.list", ProductListIn(status="needs_tax_setup"))) == ["Bread"]
    assert names(run("inventory.product.list", ProductListIn(needs_tax_setup=True))) == ["Bread"]
    assert names(run("inventory.product.list", ProductListIn(status="active"))) == []
    [sale_row] = run("inventory.product.list_for_sale", ForSaleListIn()).rows
    assert sale_row.needs_tax_setup is True
