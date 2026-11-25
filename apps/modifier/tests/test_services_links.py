"""The writes on what a modifier group applies to (MODIFIER-F05, F09): a product or a category of Inventory, the real
app (no doubles)."""

import uuid

import pytest
from live.errors import Conflict, NotFound, PermissionDenied

from apps.modifier.models import ModifierLink
from apps.modifier.schemas.links import DropIn
from apps.modifier.services.links import drop_category_links

from .conftest import FOOD, HUB_DB, ctx_for, events, group, make_category, make_product, refusal, run

pytestmark = HUB_DB


def test_linking_a_group_to_a_product_by_its_sku_and_to_a_category_by_its_name():
    sauces = group("Sauces")
    burger = make_product("Burger", "BUR-01")
    mains = make_category("Mains")
    by_product = run("modifier.link.attach", {"group": "Sauces", "product": "bur-01"})
    assert (
        by_product.target_kind,
        by_product.product_id,
        by_product.product_name,
        by_product.product_sku,
    ) == (
        "product",
        burger.id,
        "Burger",
        "BUR-01",
    )
    by_category = run(
        "modifier.link.attach", {"group_id": str(sauces.id), "category": "Mains"}
    )
    assert (
        by_category.target_kind,
        by_category.category_id,
        by_category.category_name,
        by_category.product_id,
    ) == (
        "category",
        mains.id,
        "Mains",
        None,
    )
    assert events("modifier.link.attached") == [
        {
            "id": str(by_product.id),
            "group_id": str(sauces.id),
            "product_id": str(burger.id),
            "category_id": None,
        },
        {
            "id": str(by_category.id),
            "group_id": str(sauces.id),
            "product_id": None,
            "category_id": str(mains.id),
        },
    ]
    assert ModifierLink.objects.get(pk=by_product.id).created_by == "tester"


def test_the_same_link_twice_is_a_409():
    group("Sauces")
    make_product("Burger", "BUR-01")
    run("modifier.link.attach", {"group": "Sauces", "product": "BUR-01"})
    with pytest.raises(Conflict) as error:
        run("modifier.link.attach", {"group": "Sauces", "product": "Burger"})
    assert refusal(error) == (
        "Conflict",
        "modifier.link_exists",
        {"__all__": "This group already applies there."},
    )


def test_a_deleted_or_unknown_product_or_category_cannot_be_linked():
    group("Sauces")
    burger = make_product("Burger", "BUR-01")
    run("inventory.product.delete", {"id": str(burger.id)})
    with pytest.raises(NotFound) as error:
        run("modifier.link.attach", {"group": "Sauces", "product_id": str(burger.id)})
    assert error.value.message == "This product does not exist in this hub."
    with pytest.raises(NotFound):
        run("modifier.link.attach", {"group": "Sauces", "category": "Nowhere"})


def test_detaching_by_the_link_or_by_the_group_and_the_target():
    sauces = group("Sauces")
    burger = make_product("Burger", "BUR-01")
    mains = make_category("Mains")
    by_product = run("modifier.link.attach", {"group": "Sauces", "product": "BUR-01"})
    by_category = run("modifier.link.attach", {"group": "Sauces", "category": "Mains"})
    assert run("modifier.link.detach", {"id": str(by_product.id)}).id == by_product.id
    assert (
        run(
            "modifier.link.detach", {"group": "Sauces", "category_id": str(mains.id)}
        ).id
        == by_category.id
    )
    assert ModifierLink.objects.count() == 0
    assert events("modifier.link.detached") == [
        {
            "id": str(by_product.id),
            "group_id": str(sauces.id),
            "product_id": str(burger.id),
            "category_id": None,
        },
        {
            "id": str(by_category.id),
            "group_id": str(sauces.id),
            "product_id": None,
            "category_id": str(mains.id),
        },
    ]
    # It can be linked again afterwards; detaching what is not linked is a 404.
    run("modifier.link.attach", {"group": "Sauces", "product": "BUR-01"})
    with pytest.raises(NotFound) as error:
        run("modifier.link.detach", {"group": "Sauces", "category": "Mains"})
    assert error.value.message == "This group does not apply there."


def test_the_reactions_are_the_platforms_only():
    with pytest.raises(PermissionDenied):
        run(
            "modifier.link.drop_product",
            {"id": str(uuid.uuid7())},
            ctx=ctx_for("hub_owner"),
        )
    with pytest.raises(PermissionDenied):
        drop_category_links(ctx_for("hub_owner"), DropIn(id=uuid.uuid7()))


def test_a_product_with_its_food_tax_is_still_linkable_whatever_its_category():
    group("Sauces")
    make_product("Paella", "PAE", tax=FOOD)
    assert (
        run("modifier.link.attach", {"group": "Sauces", "product": "PAE"}).product_sku
        == "PAE"
    )
