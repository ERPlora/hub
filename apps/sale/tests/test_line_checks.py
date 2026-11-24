"""Adding a product to an open check through the assistant draws no card for words that fit no product of the catalog.

Asked for «two cafés con leche» at a bar whose menu calls it «White coffee», or for «gambas a la plancha» when the menu
says «Gambas QA a la plancha», the card showed the words as they were said, and the person's yes failed with «A product
of the ticket is no longer in the catalog. Remove the line and add it again.», with no line to remove (hub#2269). The
write checks the product before its card, as Menus and Inventory do: words that fit none, or several, draw no card and
the model hears them, to look the product up or ask (SALE-F20, BASE-F97). Should the refusal still come after the yes
(the catalog changed meanwhile, or through the API), it says there is no product with those words.
"""

import pytest
from django.utils import translation
from live.errors import Conflict, InvalidPayload
from live.operations import INTERNAL, get, registry

from apps.sale.models import OrderLine
from apps.sale.tests.conftest import HUB_DB, ctx_for, run
from base import assistant
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, the_model_hears, turn_as
from base.tests.test_services_assistant import call

pytestmark = HUB_DB

ADD = "sale.order.add_line"
CHECK = "sale.order_line.check"

#: The words of the two reports, each with the product the menu really has.
UNKNOWN_WORDS = ["café con leche", "gambas a la plancha"]


@pytest.fixture
def menu(product):
    product("White coffee", "WHC", 180, "restaurant.drink")
    product("Gambas QA a la plancha", "GAM-01", 2400, "restaurant.food")
    return product("Espresso", "ESP", 130, "restaurant.drink")


@pytest.fixture
def table_4(menu):
    return str(run("sale.order.open", {"label": "Mesa 4"}).id)


def as_owner(*calls) -> dict:
    return turn_as(ctx_for("hub_admin"), *calls)


def test_the_add_line_is_checked_before_its_card():
    assert assistant.cards.check_of(get(ADD)) == CHECK


def test_the_check_is_no_tool_of_the_assistant_nor_a_route():
    op = registry[CHECK]
    assert (op.kind, op.ai, op.expose_api) == ("query", INTERNAL, False)


@pytest.mark.parametrize("words", UNKNOWN_WORDS)
def test_words_that_fit_no_product_draw_no_card_and_the_model_hears_them(table_4, words):
    plan = as_owner(call(ADD, {"order_id": table_4, "product": words, "quantity": "2"}))
    no_card_but_the_model_hears(plan, "invalid_field")
    message = f"There is no product “{words}”. Say which one."
    assert (the_model_hears(plan)["message"], the_model_hears(plan)["fields"]) == (message, {"product": message})
    assert not OrderLine.objects.filter(order_id=table_4).exists()


def test_words_that_fit_several_products_draw_no_card_and_name_them(table_4, product):
    product("Iced coffee", "ICE", 250, "restaurant.drink")
    plan = as_owner(call(ADD, {"order_id": table_4, "product": "coffee"}))
    no_card_but_the_model_hears(plan, "inventory.product_ambiguous")
    assert all(name in the_model_hears(plan)["message"] for name in ("White coffee", "Iced coffee"))


@pytest.mark.parametrize(("words", "added"), [("white coffee", "White coffee"), ("gambas qa", "Gambas QA a la plancha")])
def test_words_of_a_product_of_the_menu_draw_its_card(table_4, words, added):
    """Control: the product the words fit, as the write finds it, is the one its card shows."""
    plan = as_owner(call(ADD, {"order_id": table_4, "product": words, "quantity": "2"}))
    assert (plan["confirm"]["operation"], plan["executed"]) == (ADD, [])
    assert added in [field["value"] for field in plan["confirm"]["fields"]]


def test_a_product_named_by_its_id_draws_its_card(table_4, menu):
    plan = as_owner(call(ADD, {"order_id": table_4, "product_id": str(menu.id)}))
    assert plan["confirm"]["operation"] == ADD


# ── The write's own refusal, after the yes or through the API ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("language", "said"),
    [
        ("en", "There is no product “café con leche”. Say which one."),
        ("es", "No hay ningún producto «café con leche». Di cuál."),
    ],
)
def test_the_write_says_there_is_no_product_with_those_words(table_4, language, said):
    with translation.override(language), pytest.raises(InvalidPayload) as refused:
        run(ADD, {"order_id": table_4, "product": "café con leche"})
    assert (refused.value.code, refused.value.fields) == ("invalid_field", {"product": said})
    assert not OrderLine.objects.filter(order_id=table_4).exists()


def test_a_product_named_by_an_id_no_longer_in_the_catalog_is_no_longer_available(table_4, menu):
    """The till's line names its product by the id it read; deleted since, it is no longer in the catalog."""
    run("inventory.product.delete", {"id": str(menu.id)}, ctx_for())
    with pytest.raises(Conflict) as refused:
        run(ADD, {"order_id": table_4, "product_id": str(menu.id)})
    assert refused.value.code == "sale.product_not_available"
