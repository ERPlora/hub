"""Modifiers together with the real Inventory app (its ``requires``), without doubles.

What Inventory does to a product or a category (put it in a category, take it out, delete it) is what
the till reads from Modifiers right after, through Inventory's own operations.
"""

import pytest
from live.errors import NotFound

from apps.modifier import events
from apps.modifier.models import ModifierLink

from .conftest import A, GENERIC, make_category, make_product, run

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog():
    """«Sauces» on the category Mains, «Doneness» on the burger itself; each with one option."""
    burger = make_product("Burger", "BUR-01")
    mains = make_category("Mains")
    for name, target in (
        ("Sauces", {"category": "Mains"}),
        ("Doneness", {"product": "BUR-01"}),
    ):
        run("modifier.group.create", {"name": name})
        run("modifier.option.create", {"group": name, "name": f"{name} option"})
        run("modifier.link.attach", {"group": name, **target})
    return {"burger": burger, "mains": mains}


def carried(product: str = "BUR-01") -> list[str]:
    return [
        group.name
        for group in run("modifier.group.for_target", {"product": product}).groups
    ]


def test_putting_a_product_in_a_category_gives_it_the_categorys_groups_and_taking_it_out_takes_them(
    catalog,
):
    assert carried() == ["Doneness"]
    run("inventory.product_category.add", {"product": "BUR-01", "category": "Mains"})
    assert carried() == ["Doneness", "Sauces"]
    run("inventory.product_category.remove", {"product": "BUR-01", "category": "Mains"})
    assert carried() == ["Doneness"]


def test_a_group_is_shared_by_every_product_of_a_category(catalog):
    make_product("Hot dog", "HOT-01")
    for sku in ("BUR-01", "HOT-01"):
        run("inventory.product_category.add", {"product": sku, "category": "Mains"})
    assert carried("HOT-01") == ["Sauces"]
    assert "Sauces" in carried("BUR-01")
    sauces = run("modifier.group.list", {"search": "Sauces"}).rows[0]
    # One link (the category) serves both products.
    assert sauces.link_count == 1


def test_a_deleted_product_is_no_longer_asked_and_its_links_stop_counting(catalog):
    run("inventory.product.delete", {"product": "BUR-01"})
    with pytest.raises(NotFound):
        carried()
    doneness = run("modifier.group.list", {"search": "Doneness"}).rows[0]
    assert doneness.link_count == 0
    assert run("modifier.link.list", {"group": "Doneness"}).total == 0
    # The row is still there until Inventory's event is delivered; then it goes (MODIFIER-F09).
    assert ModifierLink.objects.filter(product_id=catalog["burger"].id).count() == 1
    events.react(A, "inventory.product.deleted", {"id": str(catalog["burger"].id)})
    assert ModifierLink.objects.filter(product_id=catalog["burger"].id).count() == 0


def test_a_deleted_category_takes_its_groups_off_its_products(catalog):
    run("inventory.product_category.add", {"product": "BUR-01", "category": "Mains"})
    run("inventory.category.delete", {"category": "Mains"})
    assert carried() == ["Doneness"]
    assert run("modifier.group.list", {"search": "Sauces"}).rows[0].link_count == 0


def test_a_renamed_product_is_shown_by_its_new_name(catalog):
    run("inventory.product.update", {"product": "BUR-01", "name": "Cheeseburger"})
    [link] = run("modifier.link.list", {"group": "Doneness"}).rows
    assert (link.product_name, link.product_sku) == ("Cheeseburger", "BUR-01")


def test_the_own_line_follows_the_products_tax_category_in_inventory(catalog):
    run("modifier.group.create", {"name": "Drinks"})
    soda = run(
        "modifier.option.create",
        {
            "group": "Drinks",
            "name": "Soda",
            "price_delta": 250,
            "tax_category_key": GENERIC,
        },
    )
    run("modifier.link.attach", {"group": "Drinks", "product": "BUR-01"})
    resolve = {"product": "BUR-01", "option_ids": [str(soda.id)]}
    assert run("modifier.selection.resolve", resolve).picks[0].own_line is True
    # The same key as the product: folded into its line.
    run("inventory.product.update", {"product": "BUR-01", "tax_category_key": GENERIC})
    valued = run("modifier.selection.resolve", resolve)
    assert (valued.picks[0].own_line, valued.folded_delta) == (False, 250)
