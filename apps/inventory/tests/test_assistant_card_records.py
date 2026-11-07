"""FIX-HUB-INVENTORY-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS (hub#526): the card of a write of Inventory says which
product or category it acts on by its name, read as whoever asks, never by its id, and leaves it out when that person
may not read it or it is not there. A product goes by its name and a category by its name, as the screens' «Delete»
dialogs and the forms' «Editing product — Vino tinto» say them; the datum that names one by its id is titled with the
screens' word for it («Producto», «Categoría»), never «Registro».
"""

import dataclasses

import pytest
from live.context import OperationContext, Scope
from live.operations import INTERNAL, get, registry

from apps.inventory.models import Category, Product
from apps.inventory.tests.conftest import A, ctx_for
from base import assistant
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs
from base.tests.test_assistant_card_values import AN_ID

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

#: Each write of Inventory and the datum of it that names a product by its id.
ON_A_PRODUCT = [
    ("inventory.product.delete", "id"),
    ("inventory.product.print_label", "id"),
    ("inventory.product.set_image", "id"),
    ("inventory.product.set_sold_out", "id"),
    ("inventory.product.update", "id"),
    ("inventory.product_category.add", "product_id"),
    ("inventory.product_category.remove", "product_id"),
    ("inventory.stock.count", "product_id"),
    ("inventory.stock.write_off", "product_id"),
]
#: Each one that names a category by its id.
ON_A_CATEGORY = [
    ("inventory.category.delete", "id"),
    ("inventory.category.update", "id"),
    ("inventory.product_category.add", "category_id"),
    ("inventory.product_category.remove", "category_id"),
]
#: Each one that names its categories by their ids, all of them.
ON_CATEGORIES = [
    ("inventory.product.create", "category_ids"),
    ("inventory.product.update", "category_ids"),
]


def make_product(name: str = "Vino tinto", sku: str = "VT-75", ean13: str = "8410000000017") -> Product:
    """A product with every datum that could name it filled (its SKU, barcode and description too), so the card that
    says its name says it by its name and no other datum."""
    return Product.objects.create(name=name, sku=sku, ean13=ean13, description=f"{name}, de la casa", price=1250)


def make_category(name: str = "Bebidas", slug: str = "bar-drinks") -> Category:
    """A category with its slug and description filled, as with a product."""
    return Category.objects.create(name=name, slug=slug, description=f"{name} del local")


def fields_of(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    card = assistant.card(get(write), arguments, language, ctx or ctx_for())
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, language: str = "en", ctx=None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, language, ctx).items()}


def without(permission: str, scope: Scope = A) -> OperationContext:
    """An admin of ``scope`` without ``permission``: a combination no role has."""
    ctx = ctx_for(scope=scope)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - {permission})


def no_id(said) -> bool:
    return not AN_ID.search(str(said))


# ── A product by its name, a category by its name ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_PRODUCT)
def test_a_write_on_a_product_says_it_by_its_name(write, datum):
    """The case the issue names, «inventory.product.delete:id»: «Product: Vino tinto», never its id nor its SKU."""
    product = make_product()
    assert shown(write, {datum: str(product.id)})[datum] == "Vino tinto"


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_CATEGORY)
def test_a_write_on_a_category_says_it_by_its_name(write, datum):
    category = make_category()
    assert shown(write, {datum: str(category.id)})[datum] == "Bebidas"


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_CATEGORIES)
def test_the_categories_of_a_product_are_said_by_their_names_in_their_order(write, datum):
    """«Categories: Bebidas, Vinos»: each one by its name, in the order sent, said in words (``named``) — never
    «1 item» of an empty line."""
    drinks, wines = make_category(), make_category("Vinos", "wine-cellar")
    arguments = {datum: [str(wines.id), str(drinks.id)]}
    if write == "inventory.product.update":
        arguments["id"] = str(make_product().id)
    field = fields_of(write, arguments)[datum]
    assert (field["value"], field.get("named")) == (["Vinos", "Bebidas"], True)


@pytest.mark.django_db
def test_a_receipt_says_each_product_it_receives_beside_its_quantity():
    wine, water = make_product(), make_product("Agua mineral", "AG-50", "8410000000024")
    items = [{"product_id": str(wine.id), "qty": "6"}, {"product_id": str(water.id), "qty": "2"}]
    said = shown("inventory.stock.receive", {"items": items, "reference": "ALB-7"})
    assert said == {
        "items": [{"product_id": "Vino tinto", "qty": "6"}, {"product_id": "Agua mineral", "qty": "2"}],
        "reference": "ALB-7",
    }


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "product", "category"), [("en", "Product", "Category"), ("es", "Producto", "Categoría")]
)
def test_the_record_a_write_names_is_titled_with_the_screens_word_in_each_language(language, product, category):
    """The id of a product or a category goes under the screens' word for it, never «Record» nor «Id»."""
    wine, drinks = make_product(), make_category()
    deleted = fields_of("inventory.product.delete", {"id": str(wine.id)}, language)["id"]
    renamed = fields_of("inventory.category.update", {"id": str(drinks.id), "name": "Bar"}, language)["id"]
    linked = fields_of(
        "inventory.product_category.add", {"product_id": str(wine.id), "category_id": str(drinks.id)}, language
    )
    assert (deleted["label"], deleted["value"], deleted.get("titled")) == (product, "Vino tinto", True)
    assert (renamed["label"], renamed["value"], renamed.get("titled")) == (category, "Bebidas", True)
    assert [(field["label"], field["value"]) for field in linked.values()] == [
        (product, "Vino tinto"),
        (category, "Bebidas"),
    ]


@pytest.mark.django_db
def test_among_several_the_card_says_the_one_the_write_names():
    """Each id names its own record, never another of the list (the first, the last)."""
    products = [make_product(), make_product("Agua mineral", "AG-50", "8410000000024")]
    categories = [make_category(), make_category("Vinos", "wine-cellar")]
    for listed in (products, list(reversed(products))):
        said = [shown("inventory.stock.write_off", {"product_id": str(p.id)})["product_id"] for p in listed]
        assert said == [p.name for p in listed]
        assert [shown("inventory.product.delete", {"id": str(p.id)})["id"] for p in listed] == [p.name for p in listed]
    for listed in (categories, list(reversed(categories))):
        said = [shown("inventory.category.delete", {"id": str(c.id)})["id"] for c in listed]
        assert said == [c.name for c in listed]
        linked = [
            shown("inventory.product_category.remove", {"product_id": str(products[0].id), "category_id": str(c.id)})
            for c in listed
        ]
        assert [each["category_id"] for each in linked] == [c.name for c in listed]


@pytest.mark.django_db
def test_a_change_keeps_saying_the_record_beside_what_it_changes():
    """The name is the record's as it is now, before the write runs: a rename says the old name under «Product» and
    the new one under its own datum."""
    wine = make_product()
    assert shown("inventory.product.update", {"id": str(wine.id), "name": "Vino de la casa"}) == {
        "id": "Vino tinto",
        "name": "Vino de la casa",
    }
    drinks = make_category()
    assert shown("inventory.category.update", {"id": str(drinks.id), "name": "Bar"}) == {"id": "Bebidas", "name": "Bar"}


# ── What is not theirs to read, or no longer there ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_PRODUCT)
def test_a_product_is_left_out_for_whoever_may_not_see_the_products(write, datum):
    """Whoever may not see the products (``inventory.view_product``) is told no product, never its id."""
    product = make_product()
    arguments = {datum: str(product.id)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("inventory.view_product"))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_CATEGORY)
def test_a_category_is_left_out_for_whoever_may_not_see_the_categories(write, datum):
    category = make_category()
    arguments = {datum: str(category.id)}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without("inventory.view_category"))
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
@pytest.mark.parametrize(("write", "datum"), ON_A_PRODUCT + ON_A_CATEGORY)
def test_what_does_not_exist_is_left_out(write, datum):
    said = shown(write, {datum: A_MISSING_ID})
    assert datum not in said
    assert no_id(said)


@pytest.mark.django_db
def test_a_record_deleted_meanwhile_is_left_out():
    """A product or a category the screens deleted (soft delete) is no longer there for the card either."""
    wine, drinks = make_product(), make_category()
    assert shown("inventory.product.delete", {"id": str(wine.id)}) == {"id": "Vino tinto"}  # positive control
    assert shown("inventory.category.delete", {"id": str(drinks.id)}) == {"id": "Bebidas"}  # positive control
    Product.objects.filter(pk=wine.pk).update(is_deleted=True)
    Category.objects.filter(pk=drinks.pk).update(is_deleted=True)
    assert shown("inventory.product.delete", {"id": str(wine.id)}) == {}
    assert shown("inventory.category.delete", {"id": str(drinks.id)}) == {}


@pytest.mark.django_db
def test_nobody_behind_the_request_reads_no_record():
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    wine = make_product()
    card = assistant.card(get("inventory.product.update"), {"id": str(wine.id), "name": "Vino de la casa"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"name": "Vino de la casa"}


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.usefixtures("no_test_fallback")
def test_a_record_of_another_business_is_left_out(hub_a, hub_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a, in_b = ctx_for(scope=Scope("host", hub_a.slug)), ctx_for(scope=Scope("host", hub_b.slug))
    with use_hub(hub_a):
        records = [
            ("inventory.product.delete", "id", make_product()),
            ("inventory.category.delete", "id", make_category()),
        ]
        for write, datum, record in records:  # positive control
            assert datum in shown(write, {datum: str(record.id)}, ctx=in_a), write
    with use_hub(hub_b):
        for write, datum, record in records:
            assert datum not in shown(write, {datum: str(record.id)}, ctx=in_b), write


# ── The read that names a category ────────────────────────────────────────────────────────────────────────────────────


def test_the_read_that_names_a_category_is_no_tool_route_nor_live_query():
    """``inventory.category.get`` exists for the card alone: the model finds a category in its list, the screens and
    the API read the list; so it is no tool of the assistant (``INTERNAL``) nor a route of the API."""
    read = registry["inventory.category.get"]
    assert (read.kind, read.permission, read.ai, read.expose_api) == (
        "query",
        "inventory.view_category",
        INTERNAL,
        False,
    )


@pytest.mark.django_db
def test_the_read_that_names_a_category_finds_it_by_its_id_or_its_name():
    drinks = make_category()
    read = get("inventory.category.get")
    assert read(ctx_for(), read.input(id=drinks.id)).name == "Bebidas"
    assert read(ctx_for(), read.input(category="bar-drinks")).id == drinks.id
