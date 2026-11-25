"""The lookups the reads and the writes share: a group or an option by its id or its name, what a group's links
count, and that every read by id asks to see the modifiers.
"""

import uuid

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from .conftest import HUB_DB, ctx_with, group, link, make_category, make_product, option, run

pytestmark = HUB_DB


def test_a_link_to_a_deleted_product_or_category_does_not_count():
    group("Sauces")
    burger = make_product()
    mains = make_category()
    link("Sauces", product_id=str(burger.id))
    link("Sauces", category_id=str(mains.id))
    run("inventory.product.delete", {"product": "Burger"})
    run("inventory.category.delete", {"category": "Mains"})
    assert run("modifier.group.list", {}).rows[0].link_count == 0


def test_a_group_by_its_id_or_its_name():
    sauces = group("Sauces")
    group("Sweet sauces")
    assert run("modifier.group.get", {"id": str(sauces.id)}).name == "Sauces"
    # The exact name first, whatever the case; else the only one that contains it.
    assert run("modifier.group.get", {"group": "SAUCES"}).id == sauces.id
    assert run("modifier.group.get", {"group": "sweet"}).name == "Sweet sauces"
    with pytest.raises(Conflict) as error:
        group("Hot sauces")
        run("modifier.group.get", {"group": "sauc"})
    assert error.value.code == "modifier.group_ambiguous"
    with pytest.raises(NotFound):
        run("modifier.group.get", {"id": str(uuid.uuid7())})


def test_an_option_by_its_id_says_its_group_as_the_question_of_two_with_one_name_does():
    of_drinks = option(group("Drinks").name, "Large")
    of_chips = option(group("Chips").name, "Large")
    assert run("modifier.option.get", {"id": str(of_drinks.id)}, role="hub_employee").label == "Large (Drinks)"
    assert run("modifier.option.get", {"id": str(of_chips.id)}).label == "Large (Chips)"
    # By its name too, as every reference of the app; two with one name ask which.
    assert run("modifier.option.get", {"option": "Large", "group": "Chips"}).id == of_chips.id
    with pytest.raises(Conflict) as error:
        run("modifier.option.get", {"option": "Large"})
    assert error.value.code == "modifier.option_ambiguous"
    with pytest.raises(NotFound):
        run("modifier.option.get", {"id": str(uuid.uuid7())})


@pytest.mark.parametrize("read", ["modifier.option.get", "modifier.link.get", "modifier.category.get"])
def test_each_read_by_id_asks_to_see_the_modifiers(read):
    with pytest.raises(PermissionDenied):
        run(read, {"id": str(uuid.uuid7())}, ctx=ctx_with("modifier.manage"))
