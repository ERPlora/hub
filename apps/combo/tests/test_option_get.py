"""``combo.option.get`` (hub#561): one choice by its id, the read that names a dish on the assistant's card of whoever
sells it. It is no tool: the model reads the menu with ``combo.combo.for_sale``."""

import dataclasses
import uuid

import pytest
from live.errors import NotFound, PermissionDenied
from live.operations import get

from apps.combo.tests.conftest import ctx_for
from base import assistant


def run(name: str, data: dict, ctx=None):
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data))


@pytest.fixture
def lentils(db):
    run(
        "inventory.product.create",
        {"name": "Lentils", "sku": "LEN", "price": 500, "tax_category_key": "restaurant.food"},
    )
    run("combo.combo.create", {"name": "Menu of the day", "price": 1350, "tax_category_key": "restaurant.food"})
    run("combo.group.create", {"combo": "Menu of the day", "name": "Starters"})
    return run("combo.option.create", {"combo": "Menu of the day", "group": "Starters", "product": "LEN"})


def test_a_choice_is_named_by_its_product(lentils):
    found = run("combo.option.get", {"id": str(lentils.id)}, ctx_for("hub_employee"))
    assert (found.id, found.product_name) == (lentils.id, "Lentils")


def test_a_choice_that_is_not_there_is_not_found(db):
    with pytest.raises(NotFound):
        run("combo.option.get", {"id": str(uuid.uuid4())})


def test_it_needs_the_right_to_see_menus(lentils):
    # Everything but this right, so it is this one the read asks for.
    everything = ctx_for()
    without = dataclasses.replace(everything, permissions=everything.permissions - {"combo.view"})
    with pytest.raises(PermissionDenied):
        run("combo.option.get", {"id": str(lentils.id)}, without)


def test_it_is_no_tool_of_the_assistant():
    assert assistant.is_tool(get("combo.option.get")) is False
