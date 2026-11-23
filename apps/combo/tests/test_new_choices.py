"""Adding the choices of a course through the assistant (COMBO-F06): a product the business does not have draws no card.

The person said «the croquettes» and the card offered «Croquetas», a product the business does not have (its own is
«Home-made croquettes»); the write refused it only after the person's yes (hub#2213). Each write that adds choices
checks the course and the products it names before its card, as the writes on a course or a choice already do: the
model hears which one is not there, and looks it up or asks.
"""

import pytest

from apps.combo.models import ChoiceOption
from apps.combo.tests.conftest import HUB_DB, ctx_for, make_combo, make_group, make_product
from base.tests.test_assistant_yes_for_its_card import no_card_but_the_model_hears, the_model_hears, turn_as
from base.tests.test_services_assistant import call

pytestmark = HUB_DB

NOT_IN_THE_CATALOGUE = "This product does not exist in this hub."


@pytest.fixture
def starters():
    """«Menú del día» with its course «Primero», and the business's croquettes and mixed salad."""
    course = make_group(make_combo("Menú del día"), "Primero")
    return course, make_product("Home-made croquettes"), make_product("Mixed salad")


def as_owner_in_english(*calls) -> dict:
    return turn_as(ctx_for("hub_admin"), *calls)


def test_a_choice_of_a_product_the_business_does_not_have_draws_no_card(starters):
    """The call the turn of hub#2213 made: the product in another language than the business's catalogue."""
    plan = as_owner_in_english(
        call("combo.option.create", {"combo": "Menú del día", "group": "Primero", "product": "Croquetas"})
    )
    no_card_but_the_model_hears(plan, "invalid_field")
    assert the_model_hears(plan)["fields"] == {"product": NOT_IN_THE_CATALOGUE}
    assert not ChoiceOption.objects.exists()


def test_the_persons_own_words_find_the_product_and_draw_its_card(starters):
    """Control: «croquettes», as the person said it, is the business's «Home-made croquettes»."""
    plan = as_owner_in_english(
        call("combo.option.create", {"combo": "Menú del día", "group": "Primero", "product": "croquettes"})
    )
    assert plan["confirm"]["operation"] == "combo.option.create"
    assert "Home-made croquettes" in [field["value"] for field in plan["confirm"]["fields"]]


def test_a_choice_by_an_id_no_product_has_draws_no_card(starters):
    """The turn of hub#2213 also offered the course's own id as a product's."""
    course, _, _ = starters
    plan = as_owner_in_english(
        call("combo.option.create", {"group_id": str(course.id), "product_id": str(course.id)})
    )
    no_card_but_the_model_hears(plan, "invalid_field")
    assert the_model_hears(plan)["fields"] == {"product_id": NOT_IN_THE_CATALOGUE}


def test_several_choices_at_once_with_one_the_business_does_not_have_draw_no_card(starters):
    course, croquettes, _ = starters
    plan = as_owner_in_english(
        call("combo.option.bulk_create", {"group_id": str(course.id), "product_ids": [str(croquettes.id), str(course.id)]})
    )
    no_card_but_the_model_hears(plan, "invalid_field")
    assert the_model_hears(plan)["fields"] == {"product_ids": NOT_IN_THE_CATALOGUE}
    assert not ChoiceOption.objects.exists()


def test_several_choices_the_business_has_draw_their_card(starters):
    """Control: the same course with two products it has."""
    course, croquettes, salad = starters
    plan = as_owner_in_english(
        call("combo.option.bulk_create", {"group_id": str(course.id), "product_ids": [str(croquettes.id), str(salad.id)]})
    )
    assert plan["confirm"]["operation"] == "combo.option.bulk_create"


@pytest.mark.parametrize("write", ["combo.option.create", "combo.option.bulk_create"])
def test_choices_for_a_course_the_menu_does_not_have_draw_no_card(starters, write):
    _, croquettes, _ = starters
    product = {"product": "croquettes"} if write == "combo.option.create" else {"product_ids": [str(croquettes.id)]}
    plan = as_owner_in_english(call(write, {"combo": "Menú del día", "group": "Entrantes", **product}))
    no_card_but_the_model_hears(plan, "not_found")


def test_a_name_several_products_fit_draws_no_card_and_names_them(starters):
    make_product("Ham croquettes")
    plan = as_owner_in_english(
        call("combo.option.create", {"combo": "Menú del día", "group": "Primero", "product": "croquettes"})
    )
    no_card_but_the_model_hears(plan, "inventory.product_ambiguous")
    assert all(name in the_model_hears(plan)["message"] for name in ("Home-made croquettes", "Ham croquettes"))
