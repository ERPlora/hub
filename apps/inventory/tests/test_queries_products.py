"""The products' reads (``apps/inventory/queries/products.py``): what the sale catalog says of each product."""

from live.operations import get

from apps.inventory.models import Product
from apps.inventory.schemas.products import ForSaleListIn

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB


def test_the_sale_catalog_says_each_products_description():
    Product.objects.create(name="Tostada", sku="TOST", price=350, description="Pan de pueblo con tomate.")
    Product.objects.create(name="Agua", sku="AGUA", price=150)

    rows = get("inventory.product.list_for_sale")(ctx_for("hub_admin"), ForSaleListIn()).rows

    assert {row.name: row.description for row in rows} == {"Tostada": "Pan de pueblo con tomate.", "Agua": ""}
