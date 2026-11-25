"""The card of a write of Inventory that names its product or its category in the person's words says the record that
the write will change, as the same search finds it, never the words said (INVENTORY-F29, BASE-F97).

In a bar with «Cheesecake» and «Tarta de queso QA», «se nos ha acabado la tarta de queso» drew «Change in Inventory:
tarta de queso · Sold out: Yes», and the person could not tell which of the two would stop selling (hub#2290). Words
that fit several products draw no card: the model hears which ones fit and asks.
"""

import dataclasses

import pytest

from apps.inventory.models import Category, Product
from apps.inventory.tests.conftest import HUB_DB, ctx_for
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, said, turn_as, yes_to
from base.tests.test_services_assistant import call

pytestmark = HUB_DB

#: Each write the assistant offers that takes its product in the person's words, with the rest of its data right.
ON_A_PRODUCT_SAID = {
    "inventory.product.update": {"product": "tarta de queso", "price": 650},
    "inventory.product.delete": {"product": "tarta de queso"},
    "inventory.product.set_sold_out": {"product": "tarta de queso", "sold_out": True},
    "inventory.product.print_label": {"product": "tarta de queso"},
    "inventory.stock.count": {"product": "tarta de queso", "stock": 3, "reason": "weekly count"},
    "inventory.stock.write_off": {"product": "tarta de queso", "qty": 1, "reason": "dropped on the floor"},
    "inventory.product_category.add": {"product": "tarta de queso", "category": "Postres"},
    "inventory.product_category.remove": {"product": "tarta de queso", "category": "Postres"},
}
#: Each one that takes its category in the person's words.
ON_A_CATEGORY_SAID = {
    "inventory.category.update": {"category": "postres", "name": "Dulces"},
    "inventory.category.delete": {"category": "postres"},
    "inventory.product_category.add": {"product": "Cheesecake", "category": "postres"},
}


@pytest.fixture
def desserts():
    """The bar of the issue: «Cheesecake» and «Tarta de queso QA», in «Postres de la casa»."""
    cheesecake = Product.objects.create(name="Cheesecake", sku="DES-01", price=550)
    tart = Product.objects.create(name="Tarta de queso QA", sku="DES-03", price=600)
    Category.objects.create(name="Postres de la casa", slug="postres-casa")
    return cheesecake, tart


def owner(language: str = "es"):
    return dataclasses.replace(ctx_for("hub_admin"), language=language)


def card_of(write: str, arguments: dict, language: str = "es") -> dict:
    plan = turn_as(owner(language), call(write, arguments))
    assert plan["confirm"] is not None, plan["executed"]
    return dict(said(plan))


def test_the_card_of_a_product_sold_out_by_the_persons_words_names_the_product_the_search_finds(desserts):
    """The case of the issue: «tarta de queso» is «Tarta de queso QA», never «Cheesecake» nor the words said."""
    for language in ("es", "en"):
        shown = card_of("inventory.product.set_sold_out", {"product": "tarta de queso", "sold_out": True}, language)
        assert shown["product"] == "Tarta de queso QA"


def test_the_yes_to_that_card_marks_sold_out_the_product_it_named(desserts):
    cheesecake, tart = desserts
    plan = turn_as(owner(), call("inventory.product.set_sold_out", {"product": "tarta de queso", "sold_out": True}))
    yes_to(plan, turn_of=lambda *calls, decision: turn_as(owner(), *calls, decision=decision))
    tart.refresh_from_db()
    cheesecake.refresh_from_db()
    assert (tart.is_sold_out, cheesecake.is_sold_out) == (True, False)


@pytest.mark.parametrize("write", ON_A_PRODUCT_SAID)
def test_every_write_that_takes_a_product_in_words_names_the_one_it_finds(desserts, write):
    assert card_of(write, ON_A_PRODUCT_SAID[write])["product"] == "Tarta de queso QA"


@pytest.mark.parametrize("write", ON_A_CATEGORY_SAID)
def test_every_write_that_takes_a_category_in_words_names_the_one_it_finds(desserts, write):
    assert card_of(write, ON_A_CATEGORY_SAID[write])["category"] == "Postres de la casa"


def test_words_that_fit_two_products_draw_no_card_and_the_model_hears_which(desserts):
    Product.objects.create(name="Tarta de queso casera", sku="DES-04", price=650)
    plan = turn_as(owner(), call("inventory.product.set_sold_out", {"product": "tarta de queso", "sold_out": True}))
    no_card_but_the_model_hears(plan, "inventory.product_ambiguous")


def test_words_beside_the_products_id_are_neither_read_nor_shown(desserts):
    """The write takes the product by its id then: the card names that one, never the one the words would find."""
    cheesecake, _ = desserts
    shown = card_of("inventory.product.set_sold_out", {"id": str(cheesecake.id), "product": "tarta de queso", "sold_out": True})
    assert (shown["id"], "product" in shown) == ("Cheesecake", False)
