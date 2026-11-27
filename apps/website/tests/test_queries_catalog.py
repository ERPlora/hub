"""The website's catalog, read from Inventory or Services by their operations' names."""

from apps.website.queries.catalog import read_catalog
from apps.website.schemas import CatalogSection
from apps.website.tests.conftest import HUB_DB, ctx_for, source_off

pytestmark = HUB_DB


def test_the_services_catalog_is_grouped_by_category_in_their_order(services_catalog):
    snapshot = read_catalog(ctx_for(None), CatalogSection(source="service"))
    assert snapshot == {
        "source": "service",
        "show_prices": True,
        "groups": [
            {
                "name": "Nails",
                "items": [
                    {"name": "Advice", "price": 0, "price_kind": "none", "minutes": 10},
                    {"name": "Manicure", "price": 2000, "price_kind": "hourly", "minutes": 45},
                ],
            },
            {"name": "Hair", "items": [{"name": "Cut", "price": 1500, "price_kind": "fixed", "minutes": 30}]},
        ],
    }


def test_the_products_catalog_lists_what_is_on_sale_by_category(products_catalog):
    snapshot = read_catalog(ctx_for(None), CatalogSection(source="inventory", show_prices=False))
    bare = {"minutes": None, "description": "", "image_url": "", "allergens": []}
    assert snapshot == {
        "source": "inventory",
        "show_prices": False,
        "groups": [
            {"name": "Food", "items": [{"name": "Bocata", "price": 550, "price_kind": "fixed", **bare}]},
            {"name": "Drinks", "items": [{"name": "Cola", "price": 250, "price_kind": "fixed", **bare}]},
            {"name": "", "items": [{"name": "Loose", "price": 0, "price_kind": "none", **bare}]},
        ],
    }


def test_a_product_the_business_hides_from_its_website_is_not_in_the_catalog(products_catalog):
    from apps.inventory.models import Product, ProductCategory

    hidden = Product.objects.create(name="Staff meal", sku="STAFF", price=500, show_on_website=False)
    ProductCategory.objects.create(product=hidden, category=products_catalog["food"])

    groups = read_catalog(ctx_for(None), CatalogSection(source="inventory"))["groups"]
    assert {group["name"]: [item["name"] for item in group["items"]] for group in groups} == {
        "Food": ["Bocata"],
        "Drinks": ["Cola"],
        "": ["Loose"],
    }


def test_a_category_filter_keeps_only_those_categories(products_catalog):
    section = CatalogSection(source="inventory", category_ids=[products_catalog["drinks"].id])
    assert [group["name"] for group in read_catalog(ctx_for(None), section)["groups"]] == ["Drinks"]


def test_a_source_whose_app_is_off_in_the_hub_is_an_empty_catalog_not_an_error(monkeypatch, products_catalog):
    # flow: WEBSITE-F05 — Inventory has products on sale, but it is not on in this hub: nothing is read from it.
    source_off(monkeypatch, "inventory")
    assert read_catalog(ctx_for(None), CatalogSection(source="inventory"))["groups"] == []


def test_no_source_is_no_catalog():
    assert read_catalog(ctx_for(None), CatalogSection()) == {"source": None, "show_prices": True, "groups": []}
