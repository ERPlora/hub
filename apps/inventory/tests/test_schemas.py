"""Input and output schemas of the inventory app: what the API, the live stream and the assistant accept."""

import uuid
from decimal import Decimal

import pydantic
import pytest

from apps.inventory import schemas
from apps.inventory.schemas import (
    CategoryIn,
    CategoryImportIn,
    CategoryListIn,
    CategoryPatchIn,
    CategoryRefIn,
    ConfigPatchIn,
    CountIn,
    MovementListIn,
    Page,
    PageIn,
    ProductCategoryIn,
    ProductImportIn,
    ProductIn,
    ProductListIn,
    ProductOut,
    ProductPage,
    ProductPatchIn,
    ProductRefIn,
    ReceiveIn,
    SaleCompletedIn,
    SaleVoidedIn,
    SummaryIn,
    LowStockListIn,
    ForSaleListIn,
    UnitListIn,
    ProductCategoryListIn,
    WriteOffIn,
)

ID = uuid.uuid7()


def invalid_fields(schema, **data):
    with pytest.raises(pydantic.ValidationError) as excinfo:
        schema(**data)
    return {
        ".".join(str(part) for part in error["loc"]) for error in excinfo.value.errors()
    }


def product(**fields):
    return {
        "name": "Coffee",
        "sku": "CAF-1",
        "price": 150,
        "tax_category_key": "general",
        **fields,
    }


# Pages


def test_page_defaults_and_bounds():
    assert PageIn().model_dump() == {"limit": 50, "offset": 0}
    assert invalid_fields(PageIn, limit=0) == {"limit"}
    assert invalid_fields(PageIn, limit=101) == {"limit"}
    assert invalid_fields(PageIn, offset=-1) == {"offset"}
    assert PageIn(limit=100).limit == 100


def test_product_page_is_the_generic_page_of_products():
    assert ProductPage is Page[ProductOut]
    assert list(ProductPage.model_fields) == ["rows", "total", "limit", "offset"]


# Lists: every filter is declared, every sort is a closed list


def test_product_list_filters():
    params = ProductListIn()
    assert (params.limit, params.sort, params.status, params.search) == (
        50,
        "name",
        None,
        None,
    )
    params = ProductListIn(
        status="needs_tax_setup",
        price_min=100,
        price_max=500,
        stock_min="0.5",
        sort="-stock",
    )
    assert (params.status, params.price_min, params.stock_min, params.sort) == (
        "needs_tax_setup",
        100,
        Decimal("0.5"),
        "-stock",
    )
    assert invalid_fields(ProductListIn, status="archived") == {"status"}
    assert invalid_fields(ProductListIn, sort="cost") == {"sort"}
    assert invalid_fields(ProductListIn, product_type="combo") == {"product_type"}
    assert invalid_fields(ProductListIn, limit=101) == {"limit"}


def test_movement_list_is_most_recent_first_by_default():
    params = MovementListIn()
    assert (params.sort, params.movement_type) == ("-created_at", None)
    assert MovementListIn(movement_type="write_off").movement_type == "write_off"
    assert invalid_fields(MovementListIn, movement_type="decrease") == {"movement_type"}
    assert invalid_fields(MovementListIn, sort="name") == {"sort"}


def test_category_list_search():
    assert CategoryListIn(search="drin").search == "drin"


def test_summary_takes_no_input():
    assert SummaryIn.model_fields == {}


# Product


def test_product_in_defaults():
    data = ProductIn(**product())
    assert data.model_dump() == {
        "name": "Coffee",
        "sku": "CAF-1",
        "price": 150,
        "tax_category_key": "general",
        "cost": 0,
        "initial_stock": Decimal("0"),
        "low_stock_threshold": None,
        "ean13": None,
        "description": "",
        "product_type": "physical",
        "unit": "ud",
        "price_quantity": Decimal("1"),
        "pricing_unit": None,
        "track_stock": None,
        "category_ids": [],
    }


def test_product_in_strips_the_texts():
    data = ProductIn(**product(name="  Coffee ", sku=" CAF-1 "))
    assert (data.name, data.sku) == ("Coffee", "CAF-1")


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"name": ""}, "name"),
        ({"name": "x" * 201}, "name"),
        ({"sku": "  "}, "sku"),
        ({"sku": "x" * 65}, "sku"),
        ({"price": -1}, "price"),
        ({"cost": -1}, "cost"),
        ({"tax_category_key": ""}, "tax_category_key"),
        ({"initial_stock": "-1"}, "initial_stock"),
        (
            {"initial_stock": "0.0001"},
            "initial_stock",
        ),  # finer than any unit's step (1 g in a kilo)
        ({"low_stock_threshold": "-1"}, "low_stock_threshold"),
        ({"ean13": "x" * 14}, "ean13"),
        ({"product_type": "combo"}, "product_type"),
        ({"unit": "lb"}, "unit"),
        ({"pricing_unit": "oz"}, "pricing_unit"),
        ({"price_quantity": "0"}, "price_quantity"),
        ({"category_ids": ["nope"]}, "category_ids.0"),
    ],
)
def test_product_in_rejects(fields, field):
    assert invalid_fields(ProductIn, **product(**fields)) == {field}


def test_product_in_requires_name_sku_price_and_tax_category():
    assert invalid_fields(ProductIn) == {"name", "sku", "price", "tax_category_key"}


def test_product_patch_carries_only_what_was_sent():
    patch = ProductPatchIn(id=ID, ean13="", track_stock=False)
    assert patch.model_dump(exclude_unset=True) == {
        "id": ID,
        "ean13": "",
        "track_stock": False,
    }
    assert invalid_fields(ProductPatchIn) == {""}  # neither its id nor its SKU or name


def test_the_sku_and_the_type_are_not_editable():
    # The SKU is the product's identity; the type is fixed at creation (WORKBOOK).
    assert invalid_fields(ProductPatchIn, id=ID, sku="NEW") == {"sku"}
    assert invalid_fields(ProductPatchIn, id=ID, product_type="service") == {
        "product_type"
    }
    assert invalid_fields(ProductPatchIn, id=ID, stock="3") == {"stock"}


def test_the_tax_category_cannot_be_emptied():
    assert invalid_fields(ProductPatchIn, id=ID, tax_category_key="") == {
        "tax_category_key"
    }


def test_product_import_takes_raw_cells_and_at_most_100_rows():
    data = ProductImportIn(
        rows=[{"line": 2, "name": "Coffee", "sku": "CAF", "price": "2,20 €"}]
    )
    [row] = data.rows
    assert (row.line, row.price, row.cost, row.unit, data.dry_run) == (
        2,
        "2,20 €",
        "",
        "",
        False,
    )
    assert invalid_fields(ProductImportIn, rows=[]) == {"rows"}
    assert invalid_fields(
        ProductImportIn, rows=[{"line": n + 2} for n in range(101)]
    ) == {"rows"}
    assert invalid_fields(ProductImportIn, rows=[{"line": 0}]) == {"rows.0.line"}


def test_a_product_category_link_needs_both_ids():
    assert invalid_fields(ProductCategoryIn, product_id=ID) == {""}  # which category?


# Categories


def test_category_in_defaults():
    assert CategoryIn(name=" Drinks ").model_dump() == {
        "name": "Drinks",
        "slug": "",
        "description": "",
        "icon": "ion:cube-outline",
        "color": "#3880ff",
        "order": 0,
        "tax_category_key": None,
    }
    assert invalid_fields(CategoryIn, name="") == {"name"}
    assert invalid_fields(CategoryIn, name="x", slug="Not A Slug") == {"slug"}
    assert invalid_fields(CategoryIn, name="x", color="red") == {"color"}
    assert invalid_fields(CategoryIn, name="x", order=-1) == {"order"}


def test_category_patch_leaves_what_was_not_sent_and_empty_clears_the_tax_category():
    patch = CategoryPatchIn(id=ID, tax_category_key="")
    assert patch.model_dump(exclude_unset=True) == {"id": ID, "tax_category_key": ""}
    assert invalid_fields(CategoryPatchIn, id=ID, is_active=False) == {"is_active"}


def test_category_import_rows():
    data = CategoryImportIn(
        rows=[{"line": 2, "name": "Drinks", "tax_category_key": "IVA 21"}]
    )
    assert (data.rows[0].slug, data.rows[0].tax_category_key) == ("", "IVA 21")
    assert invalid_fields(CategoryImportIn, rows=[]) == {"rows"}


# Stock


def test_receive_lines():
    data = ReceiveIn(
        items=[{"product_id": ID, "qty": "2.5", "unit_cost": 180}], reference=" ALB-7 "
    )
    [line] = data.items
    assert (line.qty, line.unit_cost, data.reference) == (Decimal("2.5"), 180, "ALB-7")
    assert ReceiveIn(items=[{"product_id": ID, "qty": 1}]).items[0].unit_cost is None


@pytest.mark.parametrize(
    ("line", "field"),
    [
        ({"qty": 1}, "items.0"),  # which product?
        ({"product_id": ID, "qty": 0}, "items.0.qty"),
        ({"product_id": ID, "qty": "1.0001"}, "items.0.qty"),
        ({"product_id": ID, "qty": 1, "unit_cost": -1}, "items.0.unit_cost"),
    ],
)
def test_a_bad_reception_line_says_which_line(line, field):
    assert invalid_fields(ReceiveIn, items=[line]) == {field}


def test_a_reception_has_at_least_one_line():
    assert invalid_fields(ReceiveIn, items=[]) == {"items"}


def test_a_count_is_absolute_never_negative_with_a_reason_of_3_to_500():
    data = CountIn(product_id=ID, stock="7", reason=" weekly count ")
    assert (data.stock, data.reason) == (Decimal("7"), "weekly count")
    assert invalid_fields(CountIn, product_id=ID, stock="-1", reason="count") == {
        "stock"
    }
    assert invalid_fields(CountIn, product_id=ID, stock="1", reason="ab") == {"reason"}
    assert invalid_fields(CountIn, product_id=ID, stock="1", reason="x" * 501) == {
        "reason"
    }
    assert invalid_fields(CountIn, product_id=ID, stock="1") == {"reason"}


def test_a_write_off_takes_a_positive_quantity_and_a_reason():
    assert WriteOffIn(product_id=ID, qty="2", reason="broken").qty == Decimal("2")
    assert invalid_fields(WriteOffIn, product_id=ID, qty="0", reason="broken") == {
        "qty"
    }


# Settings


def test_config_patch_leaves_what_was_not_sent():
    assert ConfigPatchIn(track_stock=False).model_dump(exclude_unset=True) == {
        "track_stock": False
    }
    assert invalid_fields(ConfigPatchIn, low_stock_threshold=-1) == {
        "low_stock_threshold"
    }
    assert invalid_fields(ConfigPatchIn, low_stock_threshold="1.5") == {
        "low_stock_threshold"
    }


# Events of other apps


def test_a_completed_sale_carries_its_lines_and_their_components():
    data = SaleCompletedIn(
        sale_id=ID,
        items=[
            {
                "product_id": ID,
                "quantity": "0.5",
                "price": 900,
            },  # what the sale adds is ignored
            {"product_id": None, "quantity": "1", "is_service": True},
            {"quantity": "3", "components": [{"product_id": ID, "quantity": "3"}]},
        ],
    )
    loose, service, menu = data.items
    assert (loose.quantity, loose.is_service, loose.components) == (
        Decimal("0.5"),
        False,
        [],
    )
    assert (service.product_id, service.is_service) == (None, True)
    assert (menu.product_id, menu.components[0].quantity) == (None, Decimal("3"))


def test_a_voided_sale_is_just_which_sale():
    assert SaleVoidedIn(sale_id=ID).sale_id == ID
    assert invalid_fields(SaleVoidedIn) == {"sale_id"}


# References: by id, or as a person says it (SKU or name) for the assistant and the voice


def test_a_product_is_named_by_its_id_or_by_its_sku_or_name():
    assert ProductRefIn(id=str(ID)).id == ID
    assert ProductRefIn(product=" red wine ").product == "red wine"
    assert invalid_fields(ProductRefIn, id="nope") == {"id"}
    assert invalid_fields(ProductRefIn) == {""}  # one of the two is needed


def test_a_category_is_named_by_its_id_or_by_its_name_or_slug():
    assert CategoryRefIn(category="Drinks").category == "Drinks"
    assert invalid_fields(CategoryRefIn) == {""}


def test_every_door_that_takes_a_product_also_takes_its_sku_or_name():
    assert ProductPatchIn(product="CAF-1", price=180).product == "CAF-1"
    assert invalid_fields(ProductPatchIn, price=180) == {""}
    assert CountIn(product="Coffee", stock="7", reason="count").product == "Coffee"
    assert invalid_fields(CountIn, stock="7", reason="count") == {""}
    assert WriteOffIn(product="red wine", qty="2", reason="broken").product == "red wine"
    assert ReceiveIn(items=[{"product": "Coffee", "qty": 1}]).items[0].product == "Coffee"
    link = ProductCategoryIn(product="Coffee", category="Drinks")
    assert (link.product_id, link.product, link.category_id, link.category) == (None, "Coffee", None, "Drinks")
    assert invalid_fields(ProductCategoryIn, product="Coffee") == {""}
    assert CategoryPatchIn(category="Drinks", name="Beverages").category == "Drinks"


# The old module's filters and orders, all kept


def test_the_product_list_keeps_the_old_filters():
    params = ProductListIn(is_active=False, needs_tax_setup=True, tracks_stock=True, category="Drinks")
    assert (params.is_active, params.needs_tax_setup, params.tracks_stock, params.category) == (False, True, True, "Drinks")


def test_low_stock_filters_and_orders():
    params = LowStockListIn()
    assert (params.sort, params.sku, params.stock_min, params.stock_max) == ("stock", None, None, None)
    assert LowStockListIn(sort="-low_stock_threshold").sort == "-low_stock_threshold"
    assert invalid_fields(LowStockListIn, sort="price") == {"sort"}


def test_category_list_filters_and_orders():
    params = CategoryListIn(name="dri", slug="dri", icon="ion:wine", color="#ff0000", product_count_min=1, product_count_max=5, sort="-product_count")
    assert (params.product_count_min, params.product_count_max, params.sort) == (1, 5, "-product_count")
    assert CategoryListIn().sort == "name"
    assert invalid_fields(CategoryListIn, sort="order") == {"sort"}


def test_movement_list_by_dates_and_by_type():
    params = MovementListIn(created_from="2026-10-01T00:00:00Z", created_to="2026-10-14T00:00:00Z", sort="movement_type")
    assert (params.created_from.day, params.created_to.day, params.sort) == (1, 14, "movement_type")


def test_every_list_has_a_search():
    for schema in (ProductListIn, LowStockListIn, ForSaleListIn, ProductCategoryListIn, CategoryListIn, MovementListIn, UnitListIn):
        assert "search" in schema.model_fields, schema.__name__


# The JSON Schema of the assistant's tools


def test_every_field_of_every_input_and_output_is_described():
    undescribed = [
        f"{name}.{field}"
        for name, schema in vars(schemas).items()
        if isinstance(schema, type) and issubclass(schema, schemas.Schema) and schema.__module__ == schemas.__name__
        for field, info in schema.model_fields.items()
        if not info.description
    ]
    assert undescribed == []
