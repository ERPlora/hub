"""Asked for a photo, the assistant offers the shared library's images by their title alone and asks which one
(COMBO-F14, INVENTORY-F30, SERVICE-F34): every tool that brings them tells the model so, and that an image's
reference (catalog:<folder>/<name>) only goes to the tool that sets it, never into the answer."""

import pytest
from live.assistant.tools import tool_spec
from live.operations import get


PROPOSING = (
    "base.catalog_image.search",
    "combo.combo.suggest_image",
    "inventory.product.suggest_image",
    "service.service.suggest_image",
)

BY_TITLE_ALONE = (
    "Name each image by its title alone and ask which one; its reference (catalog:<folder>/<name>) only goes to the "
    "tool that sets it, never in the answer, not in a table either."
)


@pytest.mark.parametrize("name", PROPOSING)
def test_the_model_offers_the_images_by_title_and_never_writes_their_reference(name):
    told = tool_spec(get(name))["description"]

    assert told.endswith(f". {BY_TITLE_ALONE}")
    assert "show them" not in told


def test_the_search_brings_the_best_match_first_with_the_reference_that_sets_it():
    told = tool_spec(get("base.catalog_image.search"))["description"]

    assert told.endswith(
        "the best match first, each with its title and the reference that sets it as the image of a product, a "
        f"service or a set menu. Empty: the whole library by title. {BY_TITLE_ALONE}"
    )


@pytest.mark.parametrize(
    ("name", "setter"),
    (
        ("combo.combo.suggest_image", "combo.combo.set_image"),
        ("inventory.product.suggest_image", "inventory.product.set_image"),
        ("service.service.suggest_image", "service.service.set_image"),
    ),
)
def test_a_suggestion_sets_none_and_names_the_write_that_sets_the_picked_one(name, setter):
    told = tool_spec(get(name))["description"]

    assert told.endswith(
        "the best matches for its name first, each with its title and its reference. It never sets one: set the one "
        f"the person picks with {setter}. {BY_TITLE_ALONE}"
    )
