"""What each read of the inventory app declares: its permission, its input and output, that it is on the API and
its tool for the assistant."""

import pytest
from live.operations import get

from apps.inventory.schemas.categories import CategoryFiltersIn, CategoryListIn, CategoryPage
from apps.inventory.schemas.exports import ExportOut
from apps.inventory.schemas.fields import ProductRefIn
from apps.inventory.schemas.movements import MovementListIn, MovementPage
from apps.inventory.schemas.product_categories import ProductCategoryListIn, ProductCategoryPage
from apps.inventory.schemas.products import (
    ForSaleListIn,
    ProductFiltersIn,
    ProductListIn,
    ProductOut,
    ProductPage,
    SaleProductPage,
)
from apps.inventory.schemas.settings import ConfigGetIn, ConfigOut
from apps.inventory.schemas.stock import LowStockListIn, LowStockPage, SummaryIn, SummaryOut
from apps.inventory.schemas.units import UnitListIn, UnitPage

from .conftest import HUB_DB

pytestmark = HUB_DB


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
    assert set(op.ai) == {"description", "asks"} and op.ai["description"]
