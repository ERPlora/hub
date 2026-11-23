"""A write of Inventory through the assistant draws no card for a product or a category the business does not have.

Asked for the dishes of a set menu, the model looked a product up by asking to change it («change the product
croquetas», with no change at all), and the person saw the card «Change in Inventory: croquetas» of a product the
business does not have; it failed only after their yes (hub#2295). Every write of Inventory that names a product or a
category checks it before its card, as the writes of Menus do: one the business does not have, or a name several fit,
draws no card, and the model hears which one to look it up or ask (INVENTORY-F02, BASE-F97).
"""

import json

import pytest
from live.operations import INTERNAL, registry

from apps.inventory.models import Category, Product, ProductCategory, StockMovement
from apps.inventory.tests.conftest import HUB_DB, ctx_for
from base import assistant
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, turn_as
from base.tests.test_services_assistant import call

pytestmark = HUB_DB

NOT_IN_THE_CATALOGUE = "This product does not exist in this hub."
NO_SUCH_CATEGORY = "This category no longer exists."

#: Each write the assistant offers that names a product the business does not have («croquetas»; its own are the
#: «Home-made croquettes»), with the rest of its data right.
ON_A_MISSING_PRODUCT = {
    "inventory.product.update": {"product": "croquetas", "price": 450},
    "inventory.product.delete": {"product": "croquetas"},
    "inventory.product.set_sold_out": {"product": "croquetas", "sold_out": True},
    "inventory.product.set_image": {"product": "croquetas", "image": ""},
    "inventory.product.print_label": {"product": "croquetas"},
    "inventory.stock.count": {"product": "croquetas", "stock": 3, "reason": "weekly count"},
    "inventory.stock.write_off": {"product": "croquetas", "qty": 1, "reason": "dropped on the floor"},
    "inventory.product_category.add": {"product": "croquetas", "category": "Starters"},
    "inventory.product_category.remove": {"product": "croquetas", "category": "Starters"},
}
#: Each one that names a category the business does not have («Desserts»).
ON_A_MISSING_CATEGORY = {
    "inventory.category.update": {"category": "Desserts", "name": "Sweets"},
    "inventory.category.delete": {"category": "Desserts"},
    "inventory.product_category.add": {"product": "croquettes", "category": "Desserts"},
    "inventory.product_category.remove": {"product": "croquettes", "category": "Desserts"},
}


@pytest.fixture
def catalogue():
    """The business's «Home-made croquettes», in its category «Starters»."""
    croquettes = Product.objects.create(name="Home-made croquettes", sku="CRO-01", price=850)
    starters = Category.objects.create(name="Starters", slug="starters")
    ProductCategory.objects.create(product=croquettes, category=starters)
    return croquettes, starters


def as_owner(*calls) -> dict:
    return turn_as(ctx_for("hub_admin"), *calls)


def the_model_hears(plan: dict) -> dict:
    return json.loads(plan["append"][0]["content"])["error"]


def test_changing_a_product_the_business_does_not_have_draws_no_card(catalogue):
    """The call the turn of hub#2295 made, looking the dish up by asking to change it."""
    plan = as_owner(call("inventory.product.update", {"product": "croquetas"}))
    no_card_but_the_model_hears(plan, "not_found")
    assert the_model_hears(plan)["message"] == NOT_IN_THE_CATALOGUE


@pytest.mark.parametrize("write", ON_A_MISSING_PRODUCT)
def test_no_write_draws_a_card_for_a_product_the_business_does_not_have(catalogue, write):
    plan = as_owner(call(write, ON_A_MISSING_PRODUCT[write]))
    no_card_but_the_model_hears(plan, "not_found")
    assert the_model_hears(plan)["message"] == NOT_IN_THE_CATALOGUE


@pytest.mark.parametrize("write", ON_A_MISSING_CATEGORY)
def test_no_write_draws_a_card_for_a_category_the_business_does_not_have(catalogue, write):
    plan = as_owner(call(write, ON_A_MISSING_CATEGORY[write]))
    no_card_but_the_model_hears(plan, "not_found")
    assert the_model_hears(plan)["message"] == NO_SUCH_CATEGORY


def test_a_reception_with_one_product_the_business_does_not_have_draws_no_card(catalogue):
    """All the lines or none, as the reception itself: the model hears which line names no product."""
    lines = [{"product": "croquettes", "qty": 10}, {"product": "croquetas", "qty": 5}]
    plan = as_owner(call("inventory.stock.receive", {"items": lines}))
    no_card_but_the_model_hears(plan, "invalid_field")
    assert the_model_hears(plan)["fields"] == {"items.1.product": NOT_IN_THE_CATALOGUE}
    assert not StockMovement.objects.exists()


def test_a_name_several_products_fit_draws_no_card_and_names_them(catalogue):
    Product.objects.create(name="Ham croquettes", sku="CRO-02", price=900)
    plan = as_owner(call("inventory.product.update", {"product": "croquettes", "price": 450}))
    no_card_but_the_model_hears(plan, "inventory.product_ambiguous")
    assert all(name in the_model_hears(plan)["message"] for name in ("Home-made croquettes", "Ham croquettes"))


@pytest.mark.parametrize(
    ("write", "arguments"),
    [
        ("inventory.product.update", {"product": "croquettes", "price": 450}),
        ("inventory.stock.count", {"product": "croquettes", "stock": 3, "reason": "weekly count"}),
        ("inventory.stock.receive", {"items": [{"product": "croquettes", "qty": 10}]}),
        ("inventory.product_category.remove", {"product": "croquettes", "category": "Starters"}),
        ("inventory.category.update", {"category": "Starters", "name": "First courses"}),
    ],
)
def test_what_the_business_has_said_in_the_persons_words_draws_its_card(catalogue, write, arguments):
    """Control: «croquettes», as the person said it, is the business's «Home-made croquettes»."""
    plan = as_owner(call(write, arguments))
    assert plan["confirm"]["operation"] == write
    assert plan["executed"] == []


def _names_a_record_as_said(op) -> bool:
    """Whether ``op``'s data names a product or a category as a person says it, on itself or on each of its lines."""
    schema = op.input.model_json_schema()
    objects = [schema, *schema.get("$defs", {}).values()]
    return any({"product", "category"} & set(found.get("properties", {})) for found in objects)


def test_every_write_the_assistant_offers_on_a_product_or_a_category_checks_it_before_its_card():
    """A new write of Inventory that names a product or a category by its words gets its check too."""
    writes = {
        name
        for name, op in registry.items()
        if op.app_label == "inventory" and op.kind == "command" and assistant.tools.is_tool(op)
    }
    naming = {name for name in writes if _names_a_record_as_said(registry[name])}
    assert naming == {*ON_A_MISSING_PRODUCT, *ON_A_MISSING_CATEGORY, "inventory.stock.receive"}
    assert {name for name in naming if not assistant.cards.check_of(registry[name])} == set()


@pytest.mark.parametrize("read", ["inventory.product.check", "inventory.product.bulk_check", "inventory.product_category.check"])
def test_the_checks_are_no_tool_of_the_assistant_nor_a_route(read):
    op = registry[read]
    assert (op.kind, op.ai, op.expose_api) == ("query", INTERNAL, False)
