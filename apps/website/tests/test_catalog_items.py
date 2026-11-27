"""What each item of the website's catalog brings: a product its photo, its description and its allergens (named in
the visitor's language when the page paints it), a service what it always brought."""

import uuid

import pytest

from apps.website.catalog_items import product_item, service_item
from apps.website.queries.catalog import read_catalog
from apps.website.render import catalog_view
from apps.website.schemas import CatalogSection
from apps.website.tests.conftest import HOST, HUB_DB, A, ctx_for, full_content, with_language
from apps.website.tests.test_services import run
from base.models import Hub

pytestmark = HUB_DB

LATTE = "catalog:hospitality/cafe_con_leche"
PHOTO = f"file:inventory/products/{uuid.uuid7().hex}.webp"


@pytest.fixture
def menu(db):
    from apps.inventory.models import Category, Product, ProductCategory

    tapas = Category.objects.create(name="Tapas", slug="tapas", order=0)
    toast = Product.objects.create(
        name="Tostada",
        sku="TOST",
        price=350,
        description="Pan de pueblo con tomate y aceite.",
        allergens=["gluten", "milk"],  # as Inventory keeps them: in the regulation's order
        image=PHOTO,
    )
    latte = Product.objects.create(name="Café con leche", sku="CAF", price=180, allergens=["milk"], image=LATTE)
    Product.objects.create(name="Agua", sku="AGUA", price=150)
    ProductCategory.objects.create(product=toast, category=tapas)
    return {"toast": toast, "latte": latte}


def own_photo_url() -> str:
    hub = Hub.objects.get(slug=A.key).id
    return f"/p/media/{hub.hex}/{PHOTO.removeprefix('file:')}"


def items(snapshot) -> dict:
    return {item["name"]: item for group in snapshot["groups"] for item in group["items"]}


def visitor(language="en"):
    from django.test import RequestFactory

    request = RequestFactory().get("/api/website/public/catalog", HTTP_HOST=HOST)
    return with_language(ctx_for(None, request=request), language)


def publish_products():
    content = full_content()
    content["catalog"] = {**content["catalog"], "source": "inventory"}
    run("website.site.save", {"template": "classic", "theme": {}, "content": content})
    run("website.site.publish")


def test_a_product_brings_its_photo_its_description_and_its_allergens(menu):
    read = items(read_catalog(ctx_for(None), CatalogSection(source="inventory")))

    assert read["Tostada"] == {
        "name": "Tostada",
        "price": 350,
        "price_kind": "fixed",
        "minutes": None,
        "description": "Pan de pueblo con tomate y aceite.",
        "image_url": own_photo_url(),
        "allergens": ["gluten", "milk"],
    }
    assert read["Café con leche"]["image_url"] == "/p/catalog/hospitality/cafe_con_leche.webp"
    assert (read["Agua"]["image_url"], read["Agua"]["description"], read["Agua"]["allergens"]) == ("", "", [])


@pytest.mark.parametrize(
    ("language", "label"), [("en", "Allergens: Gluten, Milk"), ("es", "Alérgenos: Gluten, Leche")]
)
def test_the_public_catalog_names_each_dishs_allergens_in_the_visitors_language(menu, language, label):
    publish_products()

    out = run("website.public.catalog", ctx=visitor(language))

    toast = next(item for group in out.groups for item in group.items if item.name == "Tostada")
    assert (toast.description, toast.image_url) == ("Pan de pueblo con tomate y aceite.", own_photo_url())
    assert (toast.allergens, toast.allergens_label) == (["gluten", "milk"], label)
    water = next(item for group in out.groups for item in group.items if item.name == "Agua")
    assert (water.allergens, water.allergens_label, water.image_url, water.description) == ([], "", "", "")


def test_a_service_brings_what_it_always_brought():
    row = type("Row", (), {"name": "Cut", "price": 1500, "pricing_type": "from", "duration_minutes": 30})()

    assert service_item(row) == {"name": "Cut", "price": 1500, "price_kind": "from", "minutes": 30}


def test_a_product_without_a_price_shows_none():
    row = type(
        "Row", (), {"name": "Pan", "price": 0, "description": "", "image_url": "", "allergens": ["gluten"]}
    )()

    assert product_item(row)["price_kind"] == "none"


def test_a_catalog_published_before_photos_and_allergens_paints_without_them():
    old = {"source": "inventory", "groups": [{"name": "", "items": [{"name": "Cola", "price": 250, "price_kind": "fixed"}]}]}

    [cola] = catalog_view(old, "EUR")["groups"][0]["items"]

    assert (cola["description"], cola["image_url"], cola["allergens"], cola["allergens_label"]) == ("", "", [], "")
