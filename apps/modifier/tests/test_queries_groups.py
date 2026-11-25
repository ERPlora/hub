"""The list of the groups (MODIFIER-F01) and the Inventory category a group applies to (F03)."""

import uuid

import pytest
from live.errors import NotFound

from .conftest import HUB_DB, group, link, make_category, make_product, names, option, run

pytestmark = HUB_DB


def test_the_groups_by_order_then_name_with_their_counts():
    group("Sauces", sort_order=2)
    group("Doneness", kitchen_name="POINT", min_choices=1, max_choices=1, sort_order=1)
    group("Extras", sort_order=2)
    option("Sauces", "Ketchup", is_default=True)
    option("Sauces", "Mayo")
    burger = make_product()
    link("Sauces", product_id=str(burger.id))
    link("Sauces", category_id=str(make_category().id))

    page = run("modifier.group.list", {}, role="hub_employee")
    assert (names(page), page.total, page.limit, page.offset) == (
        ["Doneness", "Extras", "Sauces"],
        3,
        50,
        0,
    )
    sauces = page.rows[2]
    assert (
        sauces.option_count,
        sauces.default_count,
        sauces.link_count,
        sauces.is_required,
    ) == (2, 1, 2, False)
    assert (page.rows[0].kitchen_name, page.rows[0].is_required) == ("POINT", True)


def test_search_filters_sort_and_pages():
    group("Sauces", kitchen_name="SALSA")
    group("Doneness", min_choices=1)
    group("Extras", max_choices=3)
    assert names(run("modifier.group.list", {"search": "salsa"})) == ["Sauces"]
    assert names(run("modifier.group.list", {"search": "ONE"})) == ["Doneness"]
    assert names(run("modifier.group.list", {"name": "x"})) == ["Extras"]
    assert names(run("modifier.group.list", {"required": True})) == ["Doneness"]
    assert names(run("modifier.group.list", {"required": False})) == [
        "Extras",
        "Sauces",
    ]
    assert names(run("modifier.group.list", {"sort": "-name"})) == [
        "Sauces",
        "Extras",
        "Doneness",
    ]
    assert names(run("modifier.group.list", {"sort": "-max_choices"}))[0] == "Extras"
    assert names(run("modifier.group.list", {"sort": "-min_choices"}))[0] == "Doneness"
    second = run("modifier.group.list", {"limit": 2, "offset": 2})
    assert (names(second), second.total) == (["Sauces"], 3)


def test_a_category_by_its_id_or_its_name_while_it_lives():
    mains = make_category("Mains")
    assert run("modifier.category.get", {"id": str(mains.id)}, role="hub_employee").name == "Mains"
    assert run("modifier.category.get", {"category": "mains"}).id == mains.id
    run("inventory.category.delete", {"category": "Mains"})
    with pytest.raises(NotFound):
        run("modifier.category.get", {"id": str(mains.id)})
    with pytest.raises(NotFound):
        run("modifier.category.get", {"id": str(uuid.uuid7())})


def test_tied_groups_follow_the_list_s_direction():
    """Groups tied on the sorted column come by name in the list's own direction, never always
    ascending; a descending list is the ascending one read backwards, ties included."""
    # Created out of name order, so that the name tie-break is not the id one (names are unique).
    for name in ("Beta", "Gamma", "Alpha"):
        group(name)
    for column in ("name", "sort_order", "min_choices", "max_choices", "option_count", "link_count"):
        up = names(run("modifier.group.list", {"sort": column}))
        down = names(run("modifier.group.list", {"sort": f"-{column}"}))
        assert (column, up, down) == (
            column,
            ["Alpha", "Beta", "Gamma"],
            ["Gamma", "Beta", "Alpha"],
        )
