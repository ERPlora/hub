"""Writes of the inventory's products: create, update, delete, restore from the copy and recover."""

import uuid
from decimal import Decimal

import pytest
from django.utils import translation
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import get

from apps.inventory import events
from apps.inventory.models import Category, Product, ProductCategory, StockMovement
from apps.inventory.schemas.fields import DeletedOut, ProductRefIn
from apps.inventory.schemas.product_images import ProductImageIn
from apps.inventory.schemas.products import ProductIn, ProductOut
from apps.inventory.tests.test_services import (
    TAX,
    clear_outbox,
    configure,
    count,
    create,
    event_names,
    general,
    movements,
    outbox,
    receive,
    refused,
    run,
    sold_out,
    update,
)
from apps.tax.models import TaxCategory
from base.tests.test_image_catalog import image_library  # noqa: F401 - the library fixture

from .conftest import A, HUB_DB, ctx_for

#: The general tax category every product of these tests takes, created before each test.
__all__ = ["general"]

pytestmark = HUB_DB

LATTE = "catalog:hospitality/cafe_con_leche"


# inventory.product.create (INVENTORY-F01, F08, F20, F26)


def test_a_product_is_created_active_unless_it_is_asked_inactive():
    """hub#1282: what a separate copy gives back comes back as it was, a product turned off included (INVENTORY-F03):
    it stays out of the till until it is turned on."""
    created, off = create("Coffee", "CAF-1"), create("Tea", "TEA-1", is_active=False)

    assert (created.is_active, off.is_active) == (True, False)
    assert dict(Product.objects.values_list("sku", "is_active")) == {"CAF-1": True, "TEA-1": False}


def test_create_a_product_with_its_categories_in_one_step():
    drinks, hot = (
        Category.objects.create(name="Drinks"),
        Category.objects.create(name="Hot"),
    )

    created = create(
        "Coffee",
        "CAF-1",
        price=150,
        cost=40,
        ean13="8412345678905",
        category_ids=[drinks.id, hot.id],
    )

    product = Product.objects.get()
    assert (
        created.id,
        created.name,
        created.sku,
        created.price,
        created.cost,
        created.ean13,
    ) == (
        product.id,
        "Coffee",
        "CAF-1",
        150,
        40,
        "8412345678905",
    )
    assert (
        created.is_active,
        created.needs_tax_setup,
        created.tax_category_key,
        created.product_type,
    ) == (True, False, TAX, "physical")
    assert set(created.category_ids) == {drinks.id, hot.id}
    assert product.created_by == "tester"
    assert outbox() == [
        (
            events.PRODUCT_CREATED,
            {
                "id": str(product.id),
                "sku": "CAF-1",
                "name": "Coffee",
                "category_ids": sorted([str(drinks.id), str(hot.id)]),
            },
        ),
        (
            events.PRODUCT_CATEGORIZED,
            {"product_id": str(product.id), "category_id": str(min(drinks.id, hot.id))},
        ),
        (
            events.PRODUCT_CATEGORIZED,
            {"product_id": str(product.id), "category_id": str(max(drinks.id, hot.id))},
        ),
    ]


def test_a_repeated_category_links_once():
    drinks = Category.objects.create(name="Drinks")
    assert create(category_ids=[drinks.id, drinks.id]).category_ids == [drinks.id]
    assert ProductCategory.objects.count() == 1


@pytest.mark.parametrize("deleted", [True, False])
def test_an_unknown_or_deleted_category_saves_nothing(deleted):
    target = (
        Category.objects.create(name="Gone", is_deleted=True).id
        if deleted
        else uuid.uuid7()
    )
    error = refused(InvalidPayload, lambda: create(category_ids=[target]))
    assert (error.status, error.code, list(error.fields)) == (
        422,
        "invalid_field",
        ["category_ids"],
    )
    assert not Product.objects.exists() and outbox() == []


def test_the_initial_stock_leaves_an_initial_movement():
    created = create("Gambas", unit="kg", initial_stock="2.5", cost=820)
    assert created.stock == Decimal("2.500")
    assert movements(created.id) == [("initial", Decimal("2.500"), Decimal("2.500"))]
    assert StockMovement.objects.get().actor == "tester"
    assert outbox(events.STOCK_CHANGED) == [
        (
            events.STOCK_CHANGED,
            {
                "product_id": str(created.id),
                "movement_type": "initial",
                "qty": "2.500",
                "stock_after": "2.500",
            },
        )
    ]


def test_without_initial_stock_there_is_no_movement():
    created = create()
    assert movements(created.id) == [] and events.STOCK_CHANGED not in event_names()


def test_the_threshold_is_born_from_the_settings_unless_given():
    configure(low_stock_threshold=25)
    assert create("Oil").low_stock_threshold == Decimal("25")
    assert create("Salt", low_stock_threshold="3").low_stock_threshold == Decimal("3")
    assert create(
        "Default when never saved", low_stock_threshold=None
    ).low_stock_threshold == Decimal("25")


def test_a_product_without_settings_is_born_with_ten():
    assert create().low_stock_threshold == Decimal("10")


def test_an_unknown_tax_category_is_refused_by_every_door():
    error = refused(InvalidPayload, lambda: create(tax_category_key="nope"))
    assert (error.code, error.fields) == (
        "invalid_field",
        {"tax_category_key": "This tax category does not exist in Taxes."},
    )
    assert not Product.objects.exists()


def test_a_sku_of_another_live_product_is_said_with_its_message():
    create("Coffee", "CAF-1")
    clear_outbox()
    error = refused(Conflict, lambda: create("Other", "CAF-1"))
    assert (error.status, error.code, error.fields) == (
        409,
        "inventory.sku_taken",
        {"sku": "That SKU already exists in the catalog."},
    )
    assert Product.objects.count() == 1 and outbox() == []


def test_an_ean13_of_another_live_product_is_said_with_its_message():
    create("Coffee", "CAF-1", ean13="8412345678905")
    error = refused(Conflict, lambda: create("Other", "OTH", ean13="8412345678905"))
    assert (error.code, list(error.fields)) == ("inventory.ean13_taken", ["ean13"])


def test_a_deleted_product_frees_its_sku_and_its_ean13():
    first = create("Coffee", "CAF-1", ean13="8412345678905")
    run("inventory.product.delete", ProductRefIn(id=first.id))
    again = create("Coffee", "CAF-1", ean13="8412345678905")
    assert again.id != first.id and again.sku == "CAF-1"


def test_the_refusal_names_the_step_of_the_unit():
    with translation.override("en"):
        error = refused(Conflict, lambda: create(unit="h", initial_stock="0.1"))
    assert "0.25 h" in error.message


def test_half_a_kilo_fits_the_kilo():
    assert create("Gambas", unit="kg", initial_stock="0.5").stock == Decimal("0.500")


def test_the_price_may_refer_to_another_quantity_of_the_same_kind():
    screw = create("Screw", price=37, price_quantity="100", pricing_unit="ud")
    assert (screw.price, screw.price_quantity, screw.pricing_unit) == (
        37,
        Decimal("100"),
        "ud",
    )
    prawns = create("Prawns", unit="g", pricing_unit="kg")
    assert (prawns.unit, prawns.pricing_unit, prawns.price_quantity) == (
        "g",
        "kg",
        Decimal("1"),
    )


def test_by_default_the_price_is_per_one_unit_of_the_product():
    created = create("Gambas", unit="kg")
    assert (created.price_quantity, created.pricing_unit) == (Decimal("1"), "kg")


def test_the_price_cannot_refer_to_a_unit_of_another_kind():
    error = refused(InvalidPayload, lambda: create(unit="kg", pricing_unit="l"))
    assert list(error.fields) == ["pricing_unit"]


def test_a_service_has_no_stock_and_never_tracks_it():
    error = refused(
        Conflict, lambda: create("Cut", product_type="service", initial_stock="1")
    )
    assert (error.code, list(error.fields)) == (
        "inventory.service_has_no_stock",
        ["initial_stock"],
    )
    cut = create("Cut", product_type="service", track_stock=True)
    assert (cut.product_type, cut.tracks_stock) == ("service", False)


def test_the_article_decides_its_own_stock_control():
    assert (
        create("A", track_stock=False).track_stock,
        create("B").track_stock,
        create("C", track_stock=True).track_stock,
    ) == (False, None, True)


def test_an_employee_cannot_create():
    refused(PermissionDenied, lambda: create(role="hub_employee"))
    assert not Product.objects.exists()


# inventory.product.update (INVENTORY-F02, F03, F05, F08, F20)


def test_update_changes_only_what_was_sent():
    created = create("Coffee", price=150, cost=40, description="keep me")
    clear_outbox()

    updated = update(created.id, name="Espresso", price=180)

    assert (
        updated.name,
        updated.price,
        updated.cost,
        updated.description,
        updated.sku,
    ) == ("Espresso", 180, 40, "keep me", "COFFEE")
    assert Product.objects.get().updated_by == "tester"
    [(name, payload)] = outbox()
    assert (
        name,
        payload["id"],
        payload["name"],
        payload["price"],
        payload["is_active"],
    ) == (
        events.PRODUCT_UPDATED,
        str(created.id),
        "Espresso",
        180,
        True,
    )


def test_an_update_without_changes_records_nothing():
    created = create("Coffee")
    clear_outbox()
    assert update(created.id, name="Coffee").id == created.id
    assert outbox() == []


def test_deactivate_and_activate():
    created = create()
    assert update(created.id, is_active=False).is_active is False
    assert update(created.id, is_active=True).is_active is True


def test_the_ean13_is_cleared_with_an_empty_text_and_left_with_null():
    created = create(ean13="8412345678905")
    assert update(created.id, ean13=None).ean13 == "8412345678905"
    assert update(created.id, ean13="").ean13 is None


def test_an_edit_can_take_the_ean13_of_a_deleted_article_but_not_of_a_live_one():
    gone = create("Gone", ean13="8412345678905")
    live = create("Live", ean13="4006381333931")
    target = create("Target")
    run("inventory.product.delete", ProductRefIn(id=gone.id))
    assert update(target.id, ean13="8412345678905").ean13 == "8412345678905"
    error = refused(Conflict, lambda: update(target.id, ean13=live.ean13))
    assert error.code == "inventory.ean13_taken"


def test_choosing_the_tax_category_ends_the_setup():
    # A product created before the tax category was mandatory (or by an old template).
    bread = Product.objects.create(name="Bread", sku="BRE", price=90)
    assert update(bread.id, tax_category_key=TAX).needs_tax_setup is False
    refused(InvalidPayload, lambda: update(bread.id, tax_category_key="nope"))


def test_the_unit_of_a_product_with_stock_does_not_change():
    gambas = create("Gambas", unit="ud", initial_stock="3")
    error = refused(Conflict, lambda: update(gambas.id, unit="kg"))
    assert (error.code, list(error.fields)) == ("inventory.unit_has_stock", ["unit"])
    count(gambas.id, "0")
    assert update(gambas.id, unit="kg").unit == "kg"


def test_the_unit_survives_an_update_that_does_not_name_it():
    gambas = create("Gambas", unit="kg")
    assert update(gambas.id, name="Prawns").unit == "kg"


def test_the_threshold_must_fit_the_unit_it_will_have():
    created = create(unit="kg")
    refused(Conflict, lambda: update(created.id, unit="ud", low_stock_threshold="0.5"))
    assert update(created.id, low_stock_threshold="0.5").low_stock_threshold == Decimal(
        "0.5"
    )


def test_the_categories_are_replaced_together_with_the_product():
    drinks, food, hot = (
        Category.objects.create(name=name) for name in ("Drinks", "Food", "Hot")
    )
    created = create(category_ids=[drinks.id, food.id])
    clear_outbox()

    updated = update(created.id, category_ids=[food.id, hot.id])

    assert set(updated.category_ids) == {food.id, hot.id}
    assert outbox() == [
        (
            events.PRODUCT_UNCATEGORIZED,
            {"product_id": str(created.id), "category_id": str(drinks.id)},
        ),
        (
            events.PRODUCT_CATEGORIZED,
            {"product_id": str(created.id), "category_id": str(hot.id)},
        ),
    ]


def test_a_failed_update_saves_neither_the_product_nor_its_categories():
    drinks = Category.objects.create(name="Drinks")
    created = create(category_ids=[drinks.id])
    refused(
        InvalidPayload,
        lambda: update(created.id, name="Changed", category_ids=[uuid.uuid7()]),
    )
    product = Product.objects.get()
    assert product.name == "Coffee" and list(product.categories.all()) == [drinks]


def test_the_stock_control_decision_is_kept_once_taken():
    created = create()
    assert update(created.id, track_stock=False).track_stock is False
    assert update(created.id, track_stock=None).track_stock is False  # null leaves it


@pytest.mark.parametrize("deleted", [True, False])
def test_updating_a_missing_or_deleted_product_is_not_found(deleted):
    target = create().id if deleted else uuid.uuid7()
    if deleted:
        run("inventory.product.delete", ProductRefIn(id=target))
    refused(NotFound, lambda: update(target, name="x"))


# inventory.product.delete (INVENTORY-F04)


def test_delete_is_logical_and_keeps_the_movements():
    created = create("Coffee", "CAF-1", initial_stock="5")
    clear_outbox()

    assert run("inventory.product.delete", ProductRefIn(id=created.id)) == DeletedOut(
        id=created.id
    )

    product = Product.objects.get()
    assert (product.is_deleted, product.is_active, product.deleted_at is not None) == (
        True,
        False,
        True,
    )
    assert len(movements(created.id)) == 1
    assert outbox() == [
        (
            events.PRODUCT_DELETED,
            {"id": str(created.id), "sku": "CAF-1", "name": "Coffee"},
        )
    ]
    refused(NotFound, lambda: run("inventory.product.delete", ProductRefIn(id=created.id)))


def test_an_employee_cannot_delete():
    created = create()
    refused(
        PermissionDenied,
        lambda: run("inventory.product.delete", ProductRefIn(id=created.id), "hub_employee"),
    )


# inventory.product.restore (INVENTORY-F34)


def restore(product_id, ctx=None, **given):
    op = get("inventory.product.restore")
    return op(ctx or system_context(A), op.input.model_validate({"id": str(product_id)} | given))


def restored_payload(product_id, sku, name, **fields):
    """What ``inventory.product.restored`` says: the product as it comes back."""
    return {
        "id": str(product_id),
        "sku": sku,
        "name": name,
        "product_type": "physical",
        "price": 100,
        "cost": 0,
        "unit": "ud",
        "tax_category_key": TAX,
        "is_active": True,
        "is_sold_out": False,
        "show_on_website": True,
        "track_stock": None,
        **fields,
    }


def test_restore_brings_a_deleted_product_back_the_same_with_its_movements_and_says_so():
    created = create("Coffee", "CAF-1", ean13="8412345678905", initial_stock="5")
    receive((created.id, "2"))
    sold_out(created.id)
    run("inventory.product.delete", ProductRefIn(id=created.id))
    clear_outbox()

    back = restore(created.id)

    # The same product: its id, its codes, its stock and every movement hang from it again; back on sale, active and
    # without the day's «sold out» it had when it was deleted.
    assert (back.id, back.sku, back.ean13, back.stock) == (created.id, "CAF-1", "8412345678905", Decimal("7.000"))
    product = Product.objects.get()
    assert (product.is_deleted, product.deleted_at, product.is_active, product.is_sold_out) == (False, None, True, False)
    # Who changed it last is whoever brought it back (the system), no longer who deleted it.
    assert product.updated_by == "system"
    assert [kind for kind, _, _ in movements(created.id)] == ["initial", "reception"]
    assert outbox() == [(events.PRODUCT_RESTORED, restored_payload(created.id, "CAF-1", "Coffee"))]


def test_restore_keeps_the_categories_it_still_has():
    drinks = Category.objects.create(name="Drinks")
    created = create("Coffee", "CAF-1", category_ids=[drinks.id])
    run("inventory.product.delete", ProductRefIn(id=created.id))

    restore(created.id)

    assert list(ProductCategory.objects.values_list("product_id", "category_id")) == [(created.id, drinks.id)]


def test_restoring_a_live_product_changes_nothing_and_says_so_again():
    # A cut before the COMMIT runs it again (repeatable): the second time finds it live.
    created = create("Coffee", "CAF-1")
    run("inventory.product.delete", ProductRefIn(id=created.id))
    restore(created.id)
    clear_outbox()

    assert restore(created.id).id == created.id

    assert Product.objects.get().is_deleted is False
    assert outbox() == [(events.PRODUCT_RESTORED, restored_payload(created.id, "CAF-1", "Coffee"))]


@pytest.mark.parametrize(
    "again, code",
    [({"sku": "CAF-1"}, "inventory.sku_taken"), ({"sku": "CAF-2", "ean13": "8412345678905"}, "inventory.ean13_taken")],
)
def test_one_whose_sku_or_ean13_another_live_product_took_since_does_not_come_back(again, code):
    first = create("Coffee", "CAF-1", ean13="8412345678905")
    run("inventory.product.delete", ProductRefIn(id=first.id))
    create("Coffee again", **again)
    clear_outbox()

    error = refused(Conflict, lambda: restore(first.id))

    assert error.code == code
    assert Product.objects.get(pk=first.id).is_deleted is True
    assert outbox() == []


def test_restoring_an_unknown_product_is_not_found():
    refused(NotFound, lambda: restore(uuid.uuid7()))
    assert outbox() == []


def test_restore_brings_back_the_image_of_the_library_it_had(image_library):  # noqa: F811
    created = create("Coffee", "CAF-1")
    run("inventory.product.set_image", ProductImageIn(id=created.id, image=LATTE))
    run("inventory.product.delete", ProductRefIn(id=created.id))

    assert restore(created.id).image == LATTE
    assert Product.objects.get().image == LATTE


def deleted_without_its_image(created) -> None:
    """``created`` deleted as deleting left a product before it kept the image of the library: without any."""
    run("inventory.product.delete", ProductRefIn(id=created.id))
    Product.objects.filter(pk=created.id).update(image="")
    clear_outbox()


def test_one_deleted_without_its_image_gets_back_the_one_of_the_library_the_copy_had(image_library):  # noqa: F811
    created = create("Coffee", "CAF-1")
    deleted_without_its_image(created)

    back = restore(created.id, image=LATTE)

    assert (back.image, Product.objects.get().image) == (LATTE, LATTE)
    # One change, as it comes back: the product is restored with it, and said once.
    assert outbox() == [(events.PRODUCT_RESTORED, restored_payload(created.id, "CAF-1", "Coffee"))]


@pytest.mark.parametrize(
    "copy",
    [
        "catalog:hospitality/gone_since",  # the library no longer has it
        # A photo of its own: deleted with the product. A fixed name: every process must collect the same test id.
        "file:inventory/products/0193a1b2c3d47e8f9a0b1c2d3e4f5a6b.webp",
    ],
)
def test_an_image_that_cannot_come_back_leaves_the_product_restored_without_any(copy, image_library):  # noqa: F811
    created = create("Coffee", "CAF-1")
    deleted_without_its_image(created)

    back = restore(created.id, image=copy)

    assert (back.is_active, back.image, Product.objects.get().image) == (True, "", "")


def test_with_the_library_unread_the_one_restored_gets_the_image_as_the_copy_had_it(settings, tmp_path):
    created = create("Coffee", "CAF-1")
    deleted_without_its_image(created)
    settings.CATALOG_DIR = str(tmp_path / "nowhere")

    assert restore(created.id, image=LATTE).image == LATTE


def test_the_image_a_deleted_product_kept_is_the_one_it_comes_back_with(image_library):  # noqa: F811
    created = create("Coffee", "CAF-1")
    run("inventory.product.set_image", ProductImageIn(id=created.id, image="catalog:hospitality/cafe_solo"))
    run("inventory.product.delete", ProductRefIn(id=created.id))

    restore(created.id, image=LATTE)

    assert Product.objects.get().image == "catalog:hospitality/cafe_solo"


def test_restoring_a_live_product_never_gives_it_an_image(image_library):  # noqa: F811
    # A cut before the COMMIT runs it again: the second time finds it live, as the business has it.
    created = create("Coffee", "CAF-1")
    clear_outbox()

    restore(created.id, image=LATTE)

    assert Product.objects.get().image == ""
    assert outbox() == [(events.PRODUCT_RESTORED, restored_payload(created.id, "CAF-1", "Coffee"))]


def test_restore_is_the_platforms_without_a_route():
    op = get("inventory.product.restore")
    assert (op.kind, op.permission, op.expose_api, op.repeatable) == ("command", "inventory.system", False, True)
    # What a recovery gives it of the product in the copy: its id, and the image it showed there.
    assert set(op.input.model_fields) == {"id", "image"}
    assert op.ai["risk"] == "normal" and op.ai["description"]
    created = create()
    run("inventory.product.delete", ProductRefIn(id=created.id))
    # Not a permission of any role: the owner holds every permission inventory declares, not this one.
    refused(PermissionDenied, lambda: restore(created.id, ctx_for("hub_owner")))
    assert Product.objects.get().is_deleted is True


# inventory.product.recover (INVENTORY-F01, INVENTORY-F30, BASE-F114)

def recover_product(ctx=None, **data):
    op = get("inventory.product.recover")
    product = {"name": "Latte", "sku": "LAT-1", "price": 250, "tax_category_key": TAX} | data
    return op(ctx or system_context(A), op.input.model_validate(product))


def test_a_product_recovered_is_created_as_its_screen_does_with_the_image_of_the_library_it_had(image_library):  # noqa: F811
    drinks = Category.objects.create(name="Drinks")

    back = recover_product(category_ids=[str(drinks.id)], is_active=False, image=LATTE)

    product = Product.objects.get()
    assert (back.id, back.image) == (product.pk, LATTE)
    assert (product.name, product.sku, product.price, product.is_active, product.image) == (
        "Latte",
        "LAT-1",
        250,
        False,
        LATTE,
    )
    assert (product.created_by, product.updated_by) == ("system", "system")
    # As the screen does it: the create with its categories, then its image.
    assert [name for name, _ in outbox()] == [
        events.PRODUCT_CREATED,
        events.PRODUCT_CATEGORIZED,
        events.PRODUCT_UPDATED,
    ]


def test_a_product_recovered_without_an_image_is_the_screens_create(image_library):  # noqa: F811
    back = recover_product()

    assert (back.image, Product.objects.get().image) == ("", "")
    assert [name for name, _ in outbox()] == [events.PRODUCT_CREATED]


def test_an_image_the_library_no_longer_has_stays_out_and_the_product_comes_back(image_library):  # noqa: F811
    back = recover_product(image="catalog:hospitality/gone_since")

    assert (back.sku, Product.objects.get().image) == ("LAT-1", "")
    assert [name for name, _ in outbox()] == [events.PRODUCT_CREATED]


def test_with_the_library_unread_the_image_comes_back_as_the_copy_had_it(settings, tmp_path):
    settings.CATALOG_DIR = str(tmp_path / "nowhere")

    back = recover_product(image=LATTE)

    assert (back.image, Product.objects.get().image) == (LATTE, LATTE)


def test_a_photo_of_its_own_never_comes_back(image_library):  # noqa: F811
    # It was deleted with the product (INVENTORY-F31), and no row may point at a file it does not own.
    back = recover_product(image=f"file:inventory/products/{uuid.uuid7().hex}.webp")

    assert (back.image, Product.objects.get().image) == ("", "")


def test_a_product_recovered_that_its_create_refuses_is_not_created(image_library):  # noqa: F811
    TaxCategory.objects.filter(key=TAX).update(is_active=False)

    error = refused(InvalidPayload, lambda: recover_product(image=LATTE))

    assert list(error.fields) == ["tax_category_key"]
    assert not Product.objects.exists()
    assert outbox() == []


def test_recovering_a_product_is_the_platforms_without_a_route():
    op = get("inventory.product.recover")
    assert (op.kind, op.permission, op.output, op.expose_api, op.repeatable) == (
        "command",
        "inventory.system",
        ProductOut,
        False,
        True,
    )
    # What the screen's create takes, and the image the product showed in the copy.
    assert issubclass(op.input, ProductIn) and "image" in op.input.model_fields
    assert op.ai["risk"] == "normal" and op.ai["description"]
    # Not a permission of any role: the owner holds every permission inventory declares, not this one.
    refused(PermissionDenied, lambda: recover_product(ctx_for("hub_owner")))
    assert not Product.objects.exists()
