"""The product searches find a name typed or said without its accents: «cafe» finds «Café con leche»."""

from live.operations import get

from apps.inventory.models import Product
from apps.inventory.schemas.fields import ProductRefIn
from apps.inventory.schemas.products import ForSaleListIn, ProductListIn

from .conftest import HUB_DB, ctx_for

pytestmark = HUB_DB


def run(name, data):
    return get(name)(ctx_for("hub_admin"), data)


def product(name, sku):
    return Product.objects.create(name=name, sku=sku, price=100)


def names(page):
    return sorted(row.name for row in page.rows)


def test_the_list_finds_a_name_typed_without_its_accents():
    product("Café con leche", "CAF-1")
    product("Café solo", "CAF-2")
    product("Té verde", "TE-1")
    assert names(run("inventory.product.list", ProductListIn(search="cafe"))) == ["Café con leche", "Café solo"]
    assert names(run("inventory.product.list", ProductListIn(name="te verde"))) == ["Té verde"]
    assert names(run("inventory.product.list", ProductListIn(search="CAFÉ CON"))) == ["Café con leche"]


def test_the_till_finds_a_name_typed_without_its_accents():
    product("Café con leche", "CAF-1")
    product("Té verde", "TE-1")
    assert names(run("inventory.product.list_for_sale", ForSaleListIn(search="cafe"))) == ["Café con leche"]


def test_the_assistant_finds_a_product_said_without_its_accents():
    latte = product("Café con leche", "CAF-1")
    product("Té verde", "TE-1")
    assert run("inventory.product.get", ProductRefIn(product="cafe con leche")).id == latte.id
