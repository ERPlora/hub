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


@pytest.mark.parametrize("name", PROPOSING)
def test_the_model_offers_the_images_by_title_and_never_writes_their_reference(name):
    told = tool_spec(get(name))["description"]

    assert "each image by its title alone and ask which one" in told
    assert "only goes to the tool that sets it, never in the answer, not in a table either" in told
    assert "show them" not in told


@pytest.mark.parametrize(
    ("name", "setter"),
    (
        ("combo.combo.suggest_image", "combo.combo.set_image"),
        ("inventory.product.suggest_image", "inventory.product.set_image"),
        ("service.service.suggest_image", "service.service.set_image"),
    ),
)
def test_a_suggestion_names_the_write_that_sets_the_picked_image(name, setter):
    told = tool_spec(get(name))["description"]

    assert f"set the one the person picks with {setter}" in told
