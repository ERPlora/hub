"""Read operations of the inventory app: lists, the product, the sale catalog, the panel and the exports."""

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from django.utils import translation
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get

from apps.inventory.models import (
    Category,
    Product,
    ProductCategory,
    Settings,
    StockMovement,
)
from apps.inventory.schemas import (
    CategoryFiltersIn,
    CategoryListIn,
    CategoryPage,
    ConfigGetIn,
    ConfigOut,
    ExportOut,
    ForSaleListIn,
    LowStockListIn,
    LowStockPage,
    MovementListIn,
    MovementPage,
    ProductCategoryListIn,
    ProductCategoryPage,
    ProductFiltersIn,
    ProductListIn,
    ProductOut,
    ProductPage,
    ProductRefIn,
    SaleProductPage,
    SummaryIn,
    SummaryOut,
    UnitListIn,
    UnitPage,
)
from apps.tax.models import TaxCategory

from .conftest import ctx_for, ctx_with

pytestmark = pytest.mark.django_db


def run(name, data, role="hub_admin"):
    return get(name)(ctx_for(role), data)


@pytest.fixture
def general(db):
    return TaxCategory.objects.create(key="product.general", name="Product — general")


def product(name, sku=None, *, tax=None, **fields):
    return Product.objects.create(
        name=name, sku=sku or name.upper(), tax_category=tax, **{"price": 100, **fields}
    )


def link(product, category):
    ProductCategory.objects.create(product=product, category=category)


def names(page):
    return [row.name for row in page.rows]


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "expose_api"),
    [
        (
            "inventory.product.list",
            "inventory.view_product",
            ProductListIn,
            ProductPage,
            True,
        ),
        ("inventory.product.get", "inventory.view_product", ProductRefIn, ProductOut, True),
        (
            "inventory.product.list_for_sale",
            "inventory.view_product",
            ForSaleListIn,
            SaleProductPage,
            True,
        ),
        (
            "inventory.product.list_low_stock",
            "inventory.view_product",
            LowStockListIn,
            LowStockPage,
            True,
        ),
        (
            "inventory.product_category.list",
            "inventory.view_product",
            ProductCategoryListIn,
            ProductCategoryPage,
            True,
        ),
        (
            "inventory.category.list",
            "inventory.view_category",
            CategoryListIn,
            CategoryPage,
            True,
        ),
        (
            "inventory.movement.list",
            "inventory.view_stock",
            MovementListIn,
            MovementPage,
            True,
        ),
        (
            "inventory.stock.get_summary",
            "inventory.view_product",
            SummaryIn,
            SummaryOut,
            True,
        ),
        ("inventory.unit.list", "inventory.view_product", UnitListIn, UnitPage, True),
        (
            "inventory.config.get",
            "inventory.manage_settings",
            ConfigGetIn,
            ConfigOut,
            True,
        ),
        (
            "inventory.product.export",
            "inventory.export_product",
            ProductFiltersIn,
            ExportOut,
            True,
        ),
        (
            "inventory.category.export",
            "inventory.export_product",
            CategoryFiltersIn,
            ExportOut,
            True,
        ),
    ],
)
def test_declarations(name, permission, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "query",
        permission,
        input,
        output,
        expose_api,
    )
    # The assistant's tool: one sentence for the model; a read carries no risk.
    assert set(op.ai) == {"description"} and op.ai["description"]


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
        "category_ids": [drinks.id],
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

    page = run("inventory.product.list_for_sale", ForSaleListIn(), role="hub_employee")

    assert [row.name for row in page.rows] == ["Coffee", "Cut", "Untaxed"]
    assert page.rows[0].model_dump() == {
        "id": coffee.id,
        "name": "Coffee",
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
        "tracks_stock": True,
    }
    assert [row.tracks_stock for row in page.rows] == [True, False, True]
    assert page.rows[2].needs_tax_setup is True
    # The till neither shows nor checks availability: the sale catalog carries no stock.
    assert "stock" not in page.rows[0].model_dump()


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
        "id",
        "name",
        "sku",
        "stock",
        "low_stock_threshold",
        "unit",
        "price_quantity",
        "pricing_unit",
    ]
    assert names(
        run("inventory.product.list_low_stock", LowStockListIn(search="c"))
    ) == ["C"]


# inventory.product_category.list


def test_the_category_map_of_the_till_has_only_active_live_products_and_live_categories():
    drinks, gone = (
        Category.objects.create(name="Drinks"),
        Category.objects.create(name="Gone", is_deleted=True),
    )
    coffee, off = product("Coffee"), product("Off", is_active=False)
    link(coffee, drinks)
    link(coffee, gone)
    link(off, drinks)

    page = run(
        "inventory.product_category.list", ProductCategoryListIn(), role="hub_employee"
    )

    assert [(row.product_id, row.category_id) for row in page.rows] == [
        (coffee.id, drinks.id)
    ]
    assert (
        run(
            "inventory.product_category.list",
            ProductCategoryListIn(category_id=gone.id),
        ).total
        == 0
    )


# inventory.category.list


def test_categories_with_how_many_active_products_each_has(general):
    drinks = Category.objects.create(
        name="Drinks", slug="drinks", tax_category=general, color="#3880ff", order=2
    )
    food = Category.objects.create(name="Food", slug="food")
    Category.objects.create(name="Gone", is_deleted=True)
    for name, active in (("Coffee", True), ("Tea", True), ("Off", False)):
        link(product(name, is_active=active), drinks)
    link(product("Deleted", is_deleted=True, is_active=False), drinks)

    page = run("inventory.category.list", CategoryListIn(), role="hub_employee")

    assert [(row.name, row.product_count) for row in page.rows] == [
        ("Drinks", 2),
        ("Food", 0),
    ]
    assert page.rows[0].model_dump() == {
        "id": drinks.id,
        "name": "Drinks",
        "slug": "drinks",
        "description": "",
        "icon": "ion:cube-outline",
        "color": "#3880ff",
        "order": 2,
        "tax_category_id": general.id,
        "tax_category_key": "product.general",
        "product_count": 2,
    }
    assert [
        row.id
        for row in run("inventory.category.list", CategoryListIn(search="foo")).rows
    ] == [food.id]


# inventory.movement.list


def movement(prod, movement_type, qty, stock_after, **fields):
    return StockMovement.objects.create(
        product=prod,
        movement_type=movement_type,
        qty=qty,
        stock_after=stock_after,
        **fields,
    )


def test_the_ledger_most_recent_first_with_the_product_it_moved():
    coffee = product("Coffee", "CAF")
    first = movement(coffee, "initial", 10, 10)
    second = movement(
        coffee, "reception", 5, 15, reference="ALB-7", unit_cost=180, actor="ana"
    )

    page = run("inventory.movement.list", MovementListIn(), role="hub_employee")

    assert [row.id for row in page.rows] == [second.id, first.id]
    assert page.rows[0].model_dump(exclude={"created_at"}) == {
        "id": second.id,
        "product_id": coffee.id,
        "product_name": "Coffee",
        "sku": "CAF",
        "movement_type": "reception",
        "qty": Decimal("5.000"),
        "stock_after": Decimal("15.000"),
        "reason": "",
        "reference": "ALB-7",
        "unit_cost": 180,
        "actor": "ana",
    }


def test_a_deleted_product_keeps_its_movements_with_its_name():
    gone = product("Gone", is_deleted=True, is_active=False)
    movement(gone, "initial", 1, 1)
    assert [
        row.product_name
        for row in run("inventory.movement.list", MovementListIn()).rows
    ] == ["Gone"]


def test_the_ledger_filters_and_searches():
    coffee, tea = product("Coffee", "CAF"), product("Tea", "TEA")
    movement(coffee, "reception", 5, 5)
    movement(coffee, "count", -1, 4, reason="broken cup")
    sale = movement(
        tea, "sale", -2, 8, reference="0199a6c0-0000-7000-8000-00000000abcd"
    )

    def listed(**filters):
        return [
            (row.product_name, row.movement_type)
            for row in run("inventory.movement.list", MovementListIn(**filters)).rows
        ]

    assert listed(movement_type="count") == [("Coffee", "count")]
    assert listed(product_id=tea.id) == [("Tea", "sale")]
    assert listed(search="caf") == [("Coffee", "count"), ("Coffee", "reception")]
    assert listed(search="abcd") == [("Tea", "sale")]
    assert listed(reference=sale.reference[-4:]) == [("Tea", "sale")]
    assert [
        row.qty
        for row in run("inventory.movement.list", MovementListIn(sort="qty")).rows
    ] == [
        Decimal("-2.000"),
        Decimal("-1.000"),
        Decimal("5.000"),
    ]


def test_an_employee_reads_the_ledger_and_a_product_editor_without_stock_rights_does_not():
    assert (
        run("inventory.movement.list", MovementListIn(), role="hub_employee").total == 0
    )
    with pytest.raises(PermissionDenied):
        get("inventory.movement.list")(
            ctx_with("inventory.view_product", "inventory.change_product"),
            MovementListIn(),
        )


# inventory.stock.get_summary


def test_the_panel_counts_tracked_articles_and_values_them_at_cost():
    threshold = {"low_stock_threshold": Decimal("5")}
    product("A", cost=200, stock=Decimal("10"), **threshold)  # in stock, valued
    product("B", cost=300, stock=Decimal("0"), **threshold)  # out
    product("C", cost=0, stock=Decimal("2"), **threshold)  # in stock, low, no cost
    product(
        "D", cost=400, stock=Decimal("-3"), **threshold
    )  # oversold: out and low, never subtracts
    product("S", cost=100, stock=Decimal("3"), product_type="service", **threshold)
    product(
        "K", cost=150, stock=Decimal("0.5"), unit="kg", **threshold
    )  # half a kilo: 75 cents
    product("U", cost=999, stock=Decimal("50"), track_stock=False)
    product("I", cost=999, stock=Decimal("50"), is_active=False)

    summary = run("inventory.stock.get_summary", SummaryIn(), role="hub_employee")

    assert summary.model_dump() == {
        "products_tracked": 5,
        "products_in_stock": 3,
        "products_out_of_stock": 2,
        "products_low_stock": 4,
        "products_without_cost": 1,
        "stock_value": 200 * 10 + 75,
        "active_products": 7,
    }


def test_the_value_rounds_half_up_to_the_cent():
    product("Saffron", cost=3, stock=Decimal("0.5"), unit="kg")  # 1.5 cents
    assert run("inventory.stock.get_summary", SummaryIn()).stock_value == 2


def test_an_empty_panel():
    assert set(
        run("inventory.stock.get_summary", SummaryIn()).model_dump().values()
    ) == {0}


# inventory.unit.list


def test_the_units_with_their_step_and_exact_factor():
    page = run("inventory.unit.list", UnitListIn(), role="hub_employee")
    assert [row.code for row in page.rows] == [
        "ud",
        "kg",
        "g",
        "t",
        "l",
        "ml",
        "min",
        "h",
    ]
    hour = page.rows[-1]
    assert (
        str(hour.name),
        hour.category,
        hour.factor_num,
        hour.factor_den,
        hour.increment,
        hour.is_reference,
    ) == (
        "Hour (h)",
        "time",
        60,
        1,
        Decimal("0.25"),
        False,
    )
    with translation.override("es"):
        assert run("inventory.unit.list", UnitListIn()).rows[0].name == "Unidad (ud)"


# inventory.config.get


def test_settings_never_saved_are_the_factory_ones():
    assert run("inventory.config.get", ConfigGetIn()).model_dump() == {
        "allow_sell_without_stock": False,
        "low_stock_threshold": 10,
        "track_stock": True,
    }


def test_saved_settings():
    Settings.objects.create(
        allow_sell_without_stock=True, low_stock_threshold=3, track_stock=False
    )
    assert run("inventory.config.get", ConfigGetIn()).model_dump() == {
        "allow_sell_without_stock": True,
        "low_stock_threshold": 3,
        "track_stock": False,
    }


def test_the_employee_does_not_see_the_settings():
    with pytest.raises(PermissionDenied):
        run("inventory.config.get", ConfigGetIn(), role="hub_employee")


# inventory.product.export and inventory.category.export


def read_csv(export, delimiter):
    assert export.content.startswith("\ufeff")  # Excel reads it as UTF-8
    return list(csv.reader(io.StringIO(export.content[1:]), delimiter=delimiter))


def test_the_export_has_every_filtered_product_not_just_a_page_with_the_import_headers(
    general,
):
    for n in range(120):
        product(f"Item {n:03}", f"IT-{n:03}", tax=general)
    product("Other", "OTH")

    with translation.override("en"):
        export = run("inventory.product.export", ProductFiltersIn(search="item"))

    assert (export.filename, export.content_type) == (
        "inventory-products.csv",
        "text/csv",
    )
    rows = read_csv(export, ",")
    assert rows[0] == [
        "Name",
        "SKU",
        "Price",
        "Cost",
        "Stock",
        "Threshold",
        "EAN-13",
        "Description",
        "Unit",
        "Tax category",
        "Active",
    ]
    assert len(rows) == 121
    assert rows[1] == [
        "Item 000",
        "IT-000",
        "€1.00",
        "€0.00",
        "0",
        "10",
        "",
        "",
        "ud",
        "product.general",
        "Yes",
    ]


def test_the_spanish_export_reads_like_the_screen_and_uses_the_semicolon_of_excel(
    general,
):
    product(
        "Gambas",
        "GAM",
        tax=general,
        price=1250,
        cost=820,
        stock=Decimal("2.500"),
        unit="kg",
        ean13="8412345678905",
        is_active=False,
    )

    with translation.override("es"):
        export = run("inventory.product.export", ProductFiltersIn())

    assert export.filename == "inventario-productos.csv"
    header, row = read_csv(export, ";")
    assert header[0] == "Nombre" and header[-2:] == ["Categoría fiscal", "Activo"]
    assert row == [
        "Gambas",
        "GAM",
        "12,50\xa0€",
        "8,20\xa0€",
        "2,5",
        "10",
        "8412345678905",
        "",
        "kg",
        "product.general",
        "No",
    ]


def test_an_empty_export_has_only_the_header():
    rows = read_csv(run("inventory.product.export", ProductFiltersIn()), ",")
    assert len(rows) == 1


def test_the_category_export():
    drinks = Category.objects.create(name="Drinks", slug="drinks")
    link(product("Coffee"), drinks)
    Category.objects.create(name="Gone", is_deleted=True)

    with translation.override("es"):
        export = run("inventory.category.export", CategoryFiltersIn())

    assert export.filename == "inventario-categorias.csv"
    assert read_csv(export, ";") == [
        ["Nombre", "Slug", "Productos"],
        ["Drinks", "drinks", "1"],
    ]


def test_without_the_export_permission_nothing_is_handed_over():
    for name, data in (
        ("inventory.product.export", ProductFiltersIn()),
        ("inventory.category.export", CategoryFiltersIn()),
    ):
        with pytest.raises(PermissionDenied):
            run(name, data, role="hub_employee")


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


def test_category_list_filters_and_orders():
    drinks = Category.objects.create(name="Drinks", slug="drinks", icon="ion:wine", color="#ff0000")
    Category.objects.create(name="Food", slug="food", icon="ion:pizza", color="#00ff00")
    for name in ("Coffee", "Tea"):
        link(product(name), drinks)

    def listed(**params):
        return [row.name for row in run("inventory.category.list", CategoryListIn(**params)).rows]

    assert listed(name="dri") == ["Drinks"]
    assert listed(slug="foo") == ["Food"]
    assert listed(icon="ion:pizza") == ["Food"]
    assert listed(color="#ff0000") == ["Drinks"]
    assert listed(product_count_min=1) == ["Drinks"]
    assert listed(product_count_max=0) == ["Food"]
    assert listed(sort="-product_count") == ["Drinks", "Food"]
    assert listed(sort="-name") == ["Food", "Drinks"]


def test_movements_by_dates_and_ordered_by_type():
    coffee = product("Coffee")
    early = movement(coffee, "reception", 5, 5)
    late = movement(coffee, "count", -1, 4)
    StockMovement.objects.filter(pk=early.pk).update(created_at=datetime(2026, 10, 1, tzinfo=UTC))
    StockMovement.objects.filter(pk=late.pk).update(created_at=datetime(2026, 10, 10, tzinfo=UTC))

    def listed(**params):
        return [row.id for row in run("inventory.movement.list", MovementListIn(**params)).rows]

    assert listed(created_from=datetime(2026, 10, 5, tzinfo=UTC)) == [late.id]
    assert listed(created_to=datetime(2026, 10, 5, tzinfo=UTC)) == [early.id]
    assert listed(sort="movement_type") == [late.id, early.id]  # count < reception


def test_every_list_searches():
    drinks = Category.objects.create(name="Drinks")
    coffee = product("Coffee", "CAF")
    link(coffee, drinks)
    link(product("Bread", "BRE"), Category.objects.create(name="Food"))

    assert names(run("inventory.product.list_for_sale", ForSaleListIn(search="caf"))) == ["Coffee"]
    assert [row.code for row in run("inventory.unit.list", UnitListIn(search="kilo")).rows] == ["kg"]
    assert [row.code for row in run("inventory.unit.list", UnitListIn(search="ml")).rows] == ["ml"]
    assert [row.product_id for row in run("inventory.product_category.list", ProductCategoryListIn(search="drin")).rows] == [coffee.id]
    assert [row.product_id for row in run("inventory.product_category.list", ProductCategoryListIn(search="caf")).rows] == [coffee.id]


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


def test_a_text_cell_a_spreadsheet_would_run_as_a_formula_gets_an_apostrophe(general):
    # =HYPERLINK(…) or @SUM(…) typed as a name would run in Excel; a negative stock is a number.
    product("=HYPERLINK(1)", "@SUM(A1)", tax=general, description="+cmd", stock=Decimal("-3"))
    link(Product.objects.get(), Category.objects.create(name="-Drinks", slug="drinks"))

    [header, row] = read_csv(run("inventory.product.export", ProductFiltersIn()), ",")
    cells = dict(zip(header, row, strict=True))
    assert (cells["Name"], cells["SKU"], cells["Description"], cells["Stock"]) == ("'=HYPERLINK(1)", "'@SUM(A1)", "'+cmd", "-3")
    assert read_csv(run("inventory.category.export", CategoryFiltersIn()), ",")[1] == ["'-Drinks", "drinks", "1"]
