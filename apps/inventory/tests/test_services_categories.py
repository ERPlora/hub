"""Writes of the inventory's categories: create, update, delete and recover."""

import uuid

from live.context import system_context
from live.errors import InvalidPayload, NotFound, PermissionDenied
from live.operations import get

from apps.inventory import events
from apps.inventory.models import Category, Product, ProductCategory
from apps.inventory.schemas.categories import CategoryIn, CategoryOut, CategoryPatchIn, CategoryRecoverIn
from apps.inventory.schemas.fields import CategoryRefIn, DeletedOut, ProductRefIn
from apps.inventory.tests.test_services import (
    TAX,
    clear_outbox,
    create,
    event_names,
    general,
    outbox,
    refused,
    run,
    update,
)
from apps.inventory.tests.test_services_products import restore
from apps.tax.models import TaxCategory

from .conftest import A, HUB_DB, ctx_for

#: The general tax category every product of these tests takes, created before each test.
__all__ = ["general"]

pytestmark = HUB_DB


# inventory.category.create, .update, .delete (INVENTORY-F06, F07)


def test_create_a_category_with_its_slug_made_from_the_name():
    created = run(
        "inventory.category.create",
        CategoryIn(name="Bebidas frías", tax_category_key=TAX),
    )
    assert (
        created.name,
        created.slug,
        created.tax_category_key,
        created.product_count,
    ) == ("Bebidas frías", "bebidas-frias", TAX, 0)
    assert Category.objects.get().created_by == "tester"
    assert outbox() == [
        (events.CATEGORY_CREATED, {"id": str(created.id), "name": "Bebidas frías"})
    ]
    assert (
        run("inventory.category.create", CategoryIn(name="Food", slug="comida")).slug
        == "comida"
    )


def test_editing_a_category_with_an_empty_slug_makes_it_again_from_the_name():
    created = run("inventory.category.create", CategoryIn(name="Drinks", slug="bar"))
    updated = run("inventory.category.update", CategoryPatchIn(id=created.id, name="Cold drinks", slug=""))
    assert (updated.name, updated.slug) == ("Cold drinks", "cold-drinks")
    kept = run("inventory.category.update", CategoryPatchIn(id=created.id, slug=""))
    assert kept.slug == "cold-drinks"


def test_a_category_with_an_unknown_tax_category_is_refused():
    error = refused(
        InvalidPayload,
        lambda: run(
            "inventory.category.create",
            CategoryIn(name="Drinks", tax_category_key="nope"),
        ),
    )
    assert list(error.fields) == ["tax_category_key"]


def test_editing_a_category_keeps_what_the_screen_does_not_show():
    created = run(
        "inventory.category.create",
        CategoryIn(
            name="Drinks", icon="ion:wine", color="#ff0000", order=3, description="cold"
        ),
    )
    clear_outbox()

    updated = run(
        "inventory.category.update",
        CategoryPatchIn(id=created.id, name="Beverages", tax_category_key=TAX),
    )

    assert (
        updated.name,
        updated.icon,
        updated.color,
        updated.order,
        updated.description,
        updated.tax_category_key,
    ) == (
        "Beverages",
        "ion:wine",
        "#ff0000",
        3,
        "cold",
        TAX,
    )
    assert outbox() == [
        (events.CATEGORY_UPDATED, {"id": str(created.id), "name": "Beverages"})
    ]
    assert (
        run(
            "inventory.category.update",
            CategoryPatchIn(id=created.id, tax_category_key=""),
        ).tax_category_key
        is None
    )


def test_a_category_update_without_changes_records_nothing():
    created = run("inventory.category.create", CategoryIn(name="Drinks"))
    clear_outbox()
    run("inventory.category.update", CategoryPatchIn(id=created.id, name="Drinks"))
    assert outbox() == []


def test_deleting_a_category_unlinks_its_products_and_never_deletes_them():
    drinks = run("inventory.category.create", CategoryIn(name="Drinks"))
    food = run("inventory.category.create", CategoryIn(name="Food"))
    wine, beer = (
        create("Wine", category_ids=[drinks.id, food.id]),
        create("Beer", category_ids=[drinks.id]),
    )
    update(beer.id, is_active=False)
    clear_outbox()

    assert run("inventory.category.delete", CategoryRefIn(id=drinks.id)) == DeletedOut(
        id=drinks.id
    )

    assert Category.objects.get(pk=drinks.id).is_deleted is True
    assert not ProductCategory.objects.filter(category_id=drinks.id).exists()
    assert list(ProductCategory.objects.values_list("product_id", "category_id")) == [
        (wine.id, food.id)
    ]
    assert Product.objects.filter(is_deleted=False).count() == 2
    assert sorted(event_names()) == sorted(
        [
            events.PRODUCT_UNCATEGORIZED,
            events.PRODUCT_UNCATEGORIZED,
            events.CATEGORY_DELETED,
        ]
    )
    refused(
        NotFound,
        lambda: run(
            "inventory.category.update", CategoryPatchIn(id=drinks.id, name="x")
        ),
    )
    refused(NotFound, lambda: run("inventory.category.delete", CategoryRefIn(id=drinks.id)))


def test_an_employee_cannot_touch_categories():
    refused(
        PermissionDenied,
        lambda: run(
            "inventory.category.create", CategoryIn(name="Drinks"), "hub_employee"
        ),
    )


# inventory.category.recover (INVENTORY-F07, INVENTORY-F34)


def recover_category(ctx=None, **data):
    op = get("inventory.category.recover")
    return op(ctx or system_context(A), op.input.model_validate(data))


def test_recover_creates_the_category_as_its_screen_does_with_its_deleted_products_back_in_it():
    cake = create("Cake", "CAK-1")
    brownie = create("Brownie", "BRO-1")
    run("inventory.product.delete", ProductRefIn(id=cake.id))
    clear_outbox()

    back = recover_category(
        name="Desserts", color="#cc0066", tax_category_key=TAX, product_ids=[str(brownie.id), str(cake.id)]
    )

    assert (back.name, back.slug, back.color, back.tax_category_key) == ("Desserts", "desserts", "#cc0066", TAX)
    made = Category.objects.get(pk=back.id)
    assert (made.created_by, made.updated_by) == ("system", "system")
    # Only the deleted one goes back in, so it comes back inside it when restored; the live one stays as it is.
    assert list(ProductCategory.objects.filter(category=made).values_list("product_id", flat=True)) == [cake.id]
    assert outbox() == [
        (events.CATEGORY_CREATED, {"id": str(back.id), "name": "Desserts"}),
        (events.PRODUCT_CATEGORIZED, {"product_id": str(cake.id), "category_id": str(back.id)}),
    ]
    restore(cake.id)
    assert list(Product.objects.get(pk=cake.id).categories.values_list("name", flat=True)) == ["Desserts"]


def test_recover_without_products_is_the_screens_create():
    back = recover_category(name="Wines", product_ids=[str(uuid.uuid7())])

    assert (back.name, back.slug, back.product_count) == ("Wines", "wines", 0)
    assert not ProductCategory.objects.exists()
    assert outbox() == [(events.CATEGORY_CREATED, {"id": str(back.id), "name": "Wines"})]


def test_recover_with_a_tax_category_no_longer_active_is_refused():
    TaxCategory.objects.filter(key=TAX).update(is_active=False)

    error = refused(InvalidPayload, lambda: recover_category(name="Desserts", tax_category_key=TAX))

    assert list(error.fields) == ["tax_category_key"]
    assert not Category.objects.exists()


def test_recover_is_the_platforms_without_a_route():
    op = get("inventory.category.recover")
    assert (op.kind, op.permission, op.input, op.output, op.expose_api, op.repeatable) == (
        "command",
        "inventory.system",
        CategoryRecoverIn,
        CategoryOut,
        False,
        True,
    )
    assert op.ai["risk"] == "normal" and op.ai["description"]
    # Not a permission of any role: the owner holds every permission inventory declares, not this one.
    refused(PermissionDenied, lambda: recover_category(ctx_for("hub_owner"), name="Desserts"))
    assert not Category.objects.exists()
