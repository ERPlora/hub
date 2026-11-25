"""A catalog read from the app that owns it, by its operations' names: every row of a list, page by page, and the
products on sale grouped by their categories, in the categories' order and those without one last. The website's
catalog and a table's menu read Inventory this way."""

import pytest
from live.context import OperationContext
from live.meta import all_live_app_configs

from base import catalog_groups
from base.tenancy.tests.business import HUB_DB, A, in_business_a

__all__ = ["in_business_a"]

pytestmark = HUB_DB


def reader() -> OperationContext:
    """Whoever may read every app's catalog."""
    permissions = frozenset(permission for config in all_live_app_configs() for permission in config.permissions)
    return OperationContext(scope=A, actor="tester", permissions=permissions, language="en")


@pytest.fixture
def menu():
    from apps.inventory.models import Category, Product, ProductCategory

    drinks = Category.objects.create(name="Drinks", slug="drinks", order=1)
    food = Category.objects.create(name="Food", slug="food", order=0)
    aperitifs = Category.objects.create(name="aperitifs", slug="aperitifs", order=1)
    gone = Category.objects.create(name="Gone", slug="gone", order=0, is_deleted=True)
    cola = Product.objects.create(name="Cola", sku="COLA", price=250)
    bocata = Product.objects.create(name="Bocata", sku="BOC", price=550)
    sangria = Product.objects.create(name="Sangria", sku="SAN", price=400)
    loose = Product.objects.create(name="Loose", sku="LOOSE", price=100)
    ProductCategory.objects.create(product=cola, category=drinks)
    ProductCategory.objects.create(product=bocata, category=food)
    ProductCategory.objects.create(product=sangria, category=drinks)
    ProductCategory.objects.create(product=sangria, category=aperitifs)
    ProductCategory.objects.create(product=loose, category=gone)
    return {"drinks": drinks, "food": food, "aperitifs": aperitifs}


def names(groups) -> list[tuple[str, list[str]]]:
    return [(name, [item["name"] for item in items]) for _category_id, name, items in groups]


def test_the_products_go_under_their_categories_in_their_order_and_those_without_one_last(menu):
    ctx = reader()
    products = catalog_groups.every_row(ctx, "inventory.product.list_for_sale")
    groups = catalog_groups.product_groups(ctx, products, lambda row: {"name": row.name})
    # Food (0) before aperitifs and Drinks (1, by name whatever its case); a product in two categories is in both;
    # one whose only category is deleted has none.
    assert names(groups) == [
        ("Food", ["Bocata"]),
        ("aperitifs", ["Sangria"]),
        ("Drinks", ["Cola", "Sangria"]),
        ("", ["Loose"]),
    ]
    assert [category_id for category_id, _name, _items in groups[:3]] == [
        str(menu["food"].id),
        str(menu["aperitifs"].id),
        str(menu["drinks"].id),
    ]


def test_only_the_products_given_are_grouped(menu):
    ctx = reader()
    some = [row for row in catalog_groups.every_row(ctx, "inventory.product.list_for_sale") if row.name != "Sangria"]
    groups = catalog_groups.product_groups(ctx, some, lambda row: {"name": row.name})
    assert names(groups) == [("Food", ["Bocata"]), ("Drinks", ["Cola"]), ("", ["Loose"])]


def test_every_row_reads_the_list_page_by_page_up_to_its_limit(monkeypatch):
    from apps.inventory.models import Product

    Product.objects.bulk_create(Product(name=f"Dish {n:03}", sku=f"D{n:03}", price=100) for n in range(5))
    monkeypatch.setattr(catalog_groups, "PAGE", 2)
    read = [row.name for row in catalog_groups.every_row(reader(), "inventory.product.list_for_sale")]
    assert read == [f"Dish {n:03}" for n in range(5)]
    capped = [row.name for row in catalog_groups.every_row(reader(), "inventory.product.list_for_sale", limit=3)]
    assert capped == ["Dish 000", "Dish 001", "Dish 002"]


def test_a_list_no_installed_app_gives_has_no_rows():
    assert list(catalog_groups.every_row(reader(), "nothing.thing.list")) == []


def test_the_group_without_a_category_goes_after_one_whose_category_is_past_the_list():
    grouped = {"": ("", [{"name": "Loose"}]), "gone": ("Archived", [{"name": "Old"}])}
    assert [name for _id, name, _items in catalog_groups.in_order(grouped, {})] == ["Archived", ""]
