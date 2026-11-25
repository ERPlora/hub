"""What the groups apply to (MODIFIER-F05): the list of links and one link, leaving out what Inventory deleted."""

import uuid

import pytest
from live.errors import NotFound

from .conftest import GENERIC, HUB_DB, group, link, make_category, make_product, run

pytestmark = HUB_DB


def test_a_link_by_its_id_says_its_group_and_what_it_hangs_from():
    group("Sauces")
    to_product = link("Sauces", product_id=str(make_product("Burger", tax=GENERIC).id))
    to_category = link("Sauces", category_id=str(make_category("Mains").id))
    assert run("modifier.link.get", {"id": str(to_product.id)}, role="hub_employee").label == "Sauces · Burger"
    assert run("modifier.link.get", {"id": str(to_category.id)}).label == "Sauces · Mains"
    # By the group and the target too, as every reference of the app.
    assert run("modifier.link.get", {"group": "Sauces", "product": "Burger"}).id == to_product.id
    assert run("modifier.link.get", {"group": "Sauces", "category": "Mains"}).id == to_category.id
    with pytest.raises(NotFound):
        run("modifier.link.get", {"id": str(uuid.uuid7())})


def test_a_link_to_what_is_deleted_is_not_there():
    group("Sauces")
    burger = make_product("Burger", tax=GENERIC)
    to_product = link("Sauces", product_id=str(burger.id))
    assert run("modifier.link.get", {"id": str(to_product.id)}).label == "Sauces · Burger"
    run("inventory.product.delete", {"product": "Burger"})
    with pytest.raises(NotFound):
        run("modifier.link.get", {"id": str(to_product.id)})


def test_the_links_of_a_group_name_their_target_and_leave_out_what_is_deleted():
    group("Sauces")
    group("Extras")
    burger = make_product("Burger", "BUR-01")
    fries = make_product("Fries", "FRI-01")
    mains = make_category("Mains")
    link("Sauces", product_id=str(fries.id))
    link("Sauces", category_id=str(mains.id))
    link("Sauces", product_id=str(burger.id))
    link("Extras", product_id=str(burger.id))

    page = run("modifier.link.list", {"group": "Sauces"}, role="hub_employee")
    # By what it names: Burger, Fries, Mains.
    assert [
        (row.target_kind, row.product_name or row.category_name) for row in page.rows
    ] == [
        ("product", "Burger"),
        ("product", "Fries"),
        ("category", "Mains"),
    ]
    assert page.rows[0].product_sku == "BUR-01"
    assert run("modifier.link.list", {"product_id": str(burger.id)}).total == 2
    assert run("modifier.link.list", {"category_id": str(mains.id)}).total == 1
    run("inventory.product.delete", {"id": str(fries.id)})
    assert [
        row.product_name for row in run("modifier.link.list", {"group": "Sauces"}).rows
    ] == ["Burger", None]
