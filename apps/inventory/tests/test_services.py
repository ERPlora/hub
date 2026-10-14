"""Write operations of the inventory app: one transaction each, with its events in the outbox.

Cases from the WORKBOOK and from the old module's batteries (ledger, stock, listeners, track_stock,
combo stock, products, category_delete, deleted_product_frees_its_code, units).
"""

import json
import threading
import uuid
from decimal import Decimal

import psycopg
import pytest
from django.db import connection, transaction
from django.utils import translation
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.inventory import events
from apps.inventory.models import (
    Category,
    Product,
    ProductCategory,
    SaleStock,
    Settings,
    StockMovement,
)
from apps.inventory.schemas import (
    CategoryImportIn,
    CategoryIn,
    CategoryOut,
    CategoryPatchIn,
    CategoryRefIn,
    ConfigOut,
    ConfigPatchIn,
    CountIn,
    DeletedOut,
    ImportReportOut,
    ProductCategoryIn,
    ProductCategoryLinkOut,
    ProductImportIn,
    ProductIn,
    ProductOut,
    ProductPatchIn,
    ProductRefIn,
    ProductsOut,
    ReceiveIn,
    SaleCompletedIn,
    SaleStockOut,
    SaleVoidedIn,
    WriteOffIn,
)
from apps.tax.models import TaxCategory

from .conftest import A, B, ctx_for, ctx_with

pytestmark = pytest.mark.django_db

TAX = "test.general"


@pytest.fixture(autouse=True)
def general(db):
    return TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})[0]


def run(name, data, role="hub_admin", scope=A):
    return get(name)(ctx_for(role, scope), data)


def system(name, data, scope=A):
    return get(name)(system_context(scope), data)


def create(name="Coffee", sku=None, role="hub_admin", **fields):
    data = ProductIn(
        **{
            "name": name,
            "sku": sku or name.upper(),
            "price": 100,
            "tax_category_key": TAX,
            **fields,
        }
    )
    return run("inventory.product.create", data, role)


def update(product_id, role="hub_admin", **fields):
    return run(
        "inventory.product.update", ProductPatchIn(id=product_id, **fields), role
    )


def receive(*lines, reference="", role="hub_admin"):
    """Each line is ``(product_id, qty)`` or ``(product_id, qty, {"unit_cost": …})``."""
    items = []
    for product_id, qty, *extra in lines:
        items.append({"product_id": product_id, "qty": qty, **(extra[0] if extra else {})})
    return run("inventory.stock.receive", ReceiveIn(items=items, reference=reference), role)


def count(product_id, stock, reason="weekly count", role="hub_admin", said=None):
    data = CountIn(product_id=product_id, product=said, stock=stock, reason=reason)
    return run("inventory.stock.count", data, role)


def write_off(product_id, qty, reason="broken", role="hub_admin", said=None):
    data = WriteOffIn(product_id=product_id, product=said, qty=qty, reason=reason)
    return run("inventory.stock.write_off", data, role)


def configure(**fields):
    return run("inventory.config.update", ConfigPatchIn(**fields))


def sell(sale_id, *items):
    return system(
        "inventory.stock.apply_sale",
        SaleCompletedIn(sale_id=sale_id, items=list(items)),
    )


def void(sale_id):
    return system("inventory.stock.restore_sale", SaleVoidedIn(sale_id=sale_id))


def line(product_id, quantity, **extra):
    return {"product_id": product_id, "quantity": quantity, **extra}


def stock_of(product_id):
    return Product.objects.get(pk=product_id).stock


def movements(product_id, movement_type=None):
    rows = StockMovement.objects.filter(product_id=product_id).order_by(
        "created_at", "id"
    )
    if movement_type:
        rows = rows.filter(movement_type=movement_type)
    return list(rows.values_list("movement_type", "qty", "stock_after"))


def outbox(*names):
    rows = OutboxEvent.objects.order_by("created_at", "id")
    if names:
        rows = rows.filter(name__in=names)
    return [(row.name, row.payload) for row in rows]


def event_names():
    return [name for name, _ in outbox()]


def clear_outbox():
    OutboxEvent.objects.all().delete()


def refused(exc_type, action):
    with pytest.raises(exc_type) as excinfo:
        action()
    return excinfo.value


# Declarations


@pytest.mark.parametrize(
    ("name", "permission", "input", "output", "risk"),
    [
        ("inventory.product.create", "inventory.add_product", ProductIn, ProductOut, "normal"),
        ("inventory.product.bulk_create", "inventory.import_product", ProductImportIn, ImportReportOut, "high"),
        ("inventory.product.update", "inventory.change_product", ProductPatchIn, ProductOut, "normal"),
        ("inventory.product.delete", "inventory.delete_product", ProductRefIn, DeletedOut, "high"),
        ("inventory.product_category.add", "inventory.change_product", ProductCategoryIn, ProductCategoryLinkOut, "normal"),
        ("inventory.product_category.remove", "inventory.change_product", ProductCategoryIn, ProductCategoryLinkOut, "normal"),
        ("inventory.category.create", "inventory.add_category", CategoryIn, CategoryOut, "normal"),
        ("inventory.category.bulk_create", "inventory.add_category", CategoryImportIn, ImportReportOut, "high"),
        ("inventory.category.update", "inventory.change_category", CategoryPatchIn, CategoryOut, "normal"),
        ("inventory.category.delete", "inventory.delete_category", CategoryRefIn, DeletedOut, "high"),
        ("inventory.stock.receive", "inventory.adjust_stock", ReceiveIn, ProductsOut, "normal"),
        ("inventory.stock.count", "inventory.adjust_stock", CountIn, ProductOut, "normal"),
        ("inventory.stock.write_off", "inventory.adjust_stock", WriteOffIn, ProductOut, "normal"),
        ("inventory.config.update", "inventory.manage_settings", ConfigPatchIn, ConfigOut, "normal"),
    ],
)
def test_declarations(name, permission, input, output, risk):
    op = get(name)
    # Every action is reachable by API (WORKBOOK, change 12) and by the assistant, with its risk.
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == ("command", permission, input, output, True)
    assert set(op.ai) == {"description", "risk"} and op.ai["description"]
    assert op.ai["risk"] == risk


@pytest.mark.parametrize(
    ("name", "input"),
    [("inventory.stock.apply_sale", SaleCompletedIn), ("inventory.stock.restore_sale", SaleVoidedIn)],
)
def test_the_reactions_to_sales_run_only_as_the_system(name, input):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "command",
        "inventory.system",
        input,
        SaleStockOut,
        False,
    )
    assert op.ai["risk"] == "high"
    # Not a permission of any role: the owner holds every permission inventory declares, not this one.
    with pytest.raises(PermissionDenied):
        op(ctx_for("hub_owner"), input(sale_id=uuid.uuid7()))


# inventory.product.create (INVENTORY-F01, F08, F20, F26)


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


# inventory.product_category.add and .remove (INVENTORY-F08)


def test_link_and_unlink_a_product_and_a_category_once():
    created, drinks = create(), Category.objects.create(name="Drinks")
    link = ProductCategoryIn(product_id=created.id, category_id=drinks.id)
    clear_outbox()

    assert run("inventory.product_category.add", link).changed is True
    assert run("inventory.product_category.add", link).changed is False
    assert run("inventory.product_category.remove", link).changed is True
    assert run("inventory.product_category.remove", link).changed is False

    payload = {"product_id": str(created.id), "category_id": str(drinks.id)}
    assert outbox() == [
        (events.PRODUCT_CATEGORIZED, payload),
        (events.PRODUCT_UNCATEGORIZED, payload),
    ]


def test_a_link_with_a_missing_product_or_category_is_not_found():
    created, drinks = create(), Category.objects.create(name="Drinks")
    refused(
        NotFound,
        lambda: run(
            "inventory.product_category.add",
            ProductCategoryIn(product_id=uuid.uuid7(), category_id=drinks.id),
        ),
    )
    refused(
        NotFound,
        lambda: run(
            "inventory.product_category.add",
            ProductCategoryIn(product_id=created.id, category_id=uuid.uuid7()),
        ),
    )


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


# inventory.category.bulk_create (INVENTORY-F10)


def import_categories(*rows):
    return run(
        "inventory.category.bulk_create",
        CategoryImportIn(rows=[{"line": n + 2, **row} for n, row in enumerate(rows)]),
    )


def test_import_categories_with_a_report_per_row():
    TaxCategory.objects.create(key="test.food", name="Restaurant food")
    run("inventory.category.create", CategoryIn(name="Drinks"))

    report = import_categories(
        {"name": "Food", "tax_category_key": "Restaurant food"},
        {"name": "drinks"},
        {"name": "Desserts", "slug": "postres", "tax_category_key": "test.food"},
        {"name": ""},
        {"name": "Wines", "tax_category_key": "IVA 99"},
        {"name": "Food"},
    )

    assert (
        report.dry_run,
        report.total,
        report.created,
        report.skipped,
        report.failed,
    ) == (False, 6, 2, 2, 2)
    assert [(row.line, row.key, row.status, row.reason) for row in report.rows] == [
        (2, "Food", "created", ""),
        (3, "drinks", "skipped", ""),
        (4, "Desserts", "created", ""),
        (5, "", "failed", "The name is missing"),
        (6, "Wines", "failed", "Tax category not recognized: IVA 99"),
        (7, "Food", "skipped", ""),
    ]
    food, desserts = (
        Category.objects.get(name="Food"),
        Category.objects.get(name="Desserts"),
    )
    assert (food.slug, food.tax_category.key, desserts.slug) == (
        "food",
        "test.food",
        "postres",
    )
    assert (
        event_names().count(events.CATEGORY_CREATED) == 3
    )  # the one by hand and the two imported


def test_repeating_a_category_file_duplicates_nothing():
    import_categories({"name": "Food"})
    assert import_categories({"name": "Food"}).skipped == 1
    assert Category.objects.count() == 1


# inventory.product.bulk_create (INVENTORY-F09)


def import_products(*rows, dry_run=False, role="hub_admin"):
    data = ProductImportIn(
        rows=[{"line": n + 2, **row} for n, row in enumerate(rows)], dry_run=dry_run
    )
    return run("inventory.product.bulk_create", data, role)


def row(sku, name=None, **cells):
    return {
        "name": sku.title() if name is None else name,
        "sku": sku,
        "price": "1",
        "tax_category_key": TAX,
        **cells,
    }


def test_the_rehearsal_checks_every_row_and_creates_nothing():
    report = import_products(row("CAF"), row("TEA", price="abc"), dry_run=True)
    assert (
        report.dry_run,
        report.total,
        report.ready,
        report.created,
        report.failed,
    ) == (True, 2, 1, 0, 1)
    assert [row.status for row in report.rows] == ["ready", "failed"]
    assert not Product.objects.exists() and outbox() == []


def test_an_import_reads_spanish_and_english_amounts_and_quantities():
    configure(low_stock_threshold=7)
    report = import_products(
        row("A", price="2,20 €", cost="1.234,56", stock="3"),
        row(
            "B",
            price="2.20",
            cost="",
            stock="2,5",
            unit="kg",
            low_stock_threshold="0,5",
        ),
        row("C", price="€1,234.50", stock=""),
        row("D", price="12,50\xa0€", ean13=" 8412345678905 ", description="The best"),
    )
    assert report.created == 4
    products = {product.sku: product for product in Product.objects.all()}
    assert (
        products["A"].price,
        products["A"].cost,
        products["A"].stock,
        products["A"].low_stock_threshold,
    ) == (220, 123456, 3, 7)
    assert (
        products["B"].price,
        products["B"].cost,
        products["B"].stock,
        products["B"].unit,
        products["B"].low_stock_threshold,
    ) == (
        220,
        0,
        Decimal("2.5"),
        "kg",
        Decimal("0.5"),
    )
    assert (products["C"].price, products["C"].stock) == (123450, 0)
    assert (products["D"].price, products["D"].ean13, products["D"].description) == (
        1250,
        "8412345678905",
        "The best",
    )


def test_an_imported_product_is_active_physical_follows_the_business_and_has_no_categories():
    import_products(row("A", stock="4"))
    product = Product.objects.get()
    assert (
        product.is_active,
        product.product_type,
        product.track_stock,
        product.categories.count(),
    ) == (True, "physical", None, 0)
    assert movements(product.id) == [("initial", Decimal("4.000"), Decimal("4.000"))]
    assert event_names() == [events.PRODUCT_CREATED, events.STOCK_CHANGED]


def test_the_import_report_says_why_each_row_did_not_go_in():
    create("Coffee", "CAF")
    deleted = create("Old", "OLD")
    run("inventory.product.delete", ProductRefIn(id=deleted.id))
    clear_outbox()

    report = import_products(
        row("CAF"),  # already in the catalog
        row("OLD"),  # a deleted product's SKU: a new product
        row("NEW", name=""),
        row("", name="No SKU"),
        row("P1", price="abc"),
        row("P2", cost="1,2,3"),
        row("NEW2"),
        row("NEW2"),
        row("Q1", stock="1.5"),
        row("Q2", stock="many"),
        row("T1", tax_category_key=""),
        row("T2", tax_category_key="iva 99"),
        row("U1", unit="lb"),
        row("E1", ean13="12345678901234"),
        row("N1", price="-3"),
    )

    assert [(row.line, row.key, row.status, row.reason) for row in report.rows] == [
        (2, "CAF", "skipped", ""),
        (3, "OLD", "created", ""),
        (4, "NEW", "failed", "Name or SKU missing"),
        (5, "", "failed", "Name or SKU missing"),
        (6, "P1", "failed", "Price is not a number"),
        (7, "P2", "failed", "Price is not a number"),
        (8, "NEW2", "created", ""),
        (9, "NEW2", "failed", "SKU repeated in the file"),
        (
            10,
            "Q1",
            "failed",
            "The quantity does not respect the step allowed for this unit",
        ),
        (11, "Q2", "failed", "Quantity is not a number"),
        (12, "T1", "failed", "The tax category is missing"),
        (13, "T2", "failed", "Tax category not recognized: iva 99"),
        (14, "U1", "failed", "Unit of measure not recognized: lb"),
        (15, "E1", "failed", "A text is longer than its column allows"),
        (16, "N1", "failed", "Price is not a number"),
    ]
    assert (report.total, report.created, report.skipped, report.failed) == (
        15,
        2,
        1,
        12,
    )
    assert (
        Product.objects.get(sku="CAF", is_deleted=False).name == "Coffee"
    )  # the existing one is not touched


def test_an_imported_ean13_of_a_live_product_fails_that_row_only():
    create("Coffee", "CAF", ean13="8412345678905")
    report = import_products(row("A", ean13="8412345678905"), row("B"))
    assert [(row.status, row.reason) for row in report.rows] == [
        ("failed", "Another product of the catalog already has that EAN-13."),
        ("created", ""),
    ]


def test_importing_needs_its_own_permission():
    refused(PermissionDenied, lambda: import_products(row("A"), role="hub_employee"))
    refused(
        PermissionDenied,
        lambda: get("inventory.product.bulk_create")(
            ctx_with("inventory.add_product"), ProductImportIn(rows=[{"line": 2}])
        ),
    )


# inventory.stock.receive (INVENTORY-F13)


def test_receiving_raises_the_stock_writes_a_reception_and_updates_the_cost():
    coffee = create("Coffee", cost=200, initial_stock="10", low_stock_threshold="5")
    clear_outbox()

    [after] = receive((coffee.id, "4", {"unit_cost": 180}), reference="ALB-7").rows

    assert (after.stock, after.cost) == (Decimal("14"), 180)
    movement = StockMovement.objects.get(movement_type="reception")
    assert (
        movement.qty,
        movement.stock_after,
        movement.unit_cost,
        movement.reference,
        movement.actor,
    ) == (
        Decimal("4"),
        Decimal("14"),
        180,
        "ALB-7",
        "tester",
    )
    assert outbox() == [
        (
            events.STOCK_CHANGED,
            {
                "product_id": str(coffee.id),
                "movement_type": "reception",
                "qty": "4.000",
                "stock_after": "14.000",
            },
        )
    ]


def test_receiving_without_a_cost_keeps_the_cost_it_had():
    coffee = create("Coffee", cost=500)
    receive((coffee.id, "3"))
    assert Product.objects.get().cost == 500
    assert StockMovement.objects.get().unit_cost is None
    receive((coffee.id, "2", {"unit_cost": 700}))
    assert (Product.objects.get().cost, stock_of(coffee.id)) == (700, Decimal("5"))


def test_a_reception_of_several_products_and_the_same_one_twice():
    coffee, tea = create("Coffee"), create("Tea")
    rows = receive((coffee.id, "1"), (tea.id, "2"), (coffee.id, "3")).rows
    assert {row.name: row.stock for row in rows} == {
        "Coffee": Decimal("4"),
        "Tea": Decimal("2"),
    }
    assert movements(coffee.id) == [
        ("reception", Decimal("1"), Decimal("1")),
        ("reception", Decimal("3"), Decimal("4")),
    ]


def test_a_reception_applies_to_an_article_without_stock_control():
    created = create(track_stock=False)
    receive((created.id, "5"))
    assert stock_of(created.id) == Decimal("5")


def test_half_a_kilo_received_is_half_a_kilo():
    gambas = create("Gambas", unit="kg")
    receive((gambas.id, "2.5"))
    receive((gambas.id, "0.5"))
    assert stock_of(gambas.id) == Decimal("3")


@pytest.mark.parametrize("bad", ["missing", "service", "off_grid"])
def test_a_reception_with_a_bad_line_is_refused_whole_saying_which_line(bad):
    coffee = create("Coffee")
    cut = create("Cut", product_type="service")
    bad_line = {
        "missing": (uuid.uuid7(), "1"),
        "service": (cut.id, "1"),
        "off_grid": (coffee.id, "1.5"),
    }[bad]
    clear_outbox()

    with pytest.raises((InvalidPayload, Conflict)) as excinfo:
        receive((coffee.id, "2"), bad_line)

    error = excinfo.value
    expected = {
        "missing": (422, "invalid_field", "items.1.product_id"),
        "service": (409, "inventory.service_has_no_stock", "items.1.product_id"),
        "off_grid": (409, "inventory.off_grid_quantity", "items.1.qty"),
    }[bad]
    assert (error.status, error.code, list(error.fields)) == (
        expected[0],
        expected[1],
        [expected[2]],
    )
    assert (
        stock_of(coffee.id) == 0
        and not StockMovement.objects.exists()
        and outbox() == []
    )


def test_a_reception_that_lifts_a_tracked_article_above_its_threshold_says_it_recovered():
    low = create("Low", "LOW", initial_stock="2", low_stock_threshold="5")
    clear_outbox()

    receive((low.id, "1"), (low.id, "3"), reference="ALB-9")

    assert outbox(events.STOCK_THRESHOLD_CROSSED) == [
        (
            events.STOCK_THRESHOLD_CROSSED,
            {
                "product_id": str(low.id),
                "sku": "LOW",
                "name": "Low",
                "previous_quantity": "2.000",
                "current_quantity": "6.000",
                "low_stock_threshold": "5.000",
                "crossing": "recovered",
                "movement_type": "reception",
                "reference": "ALB-9",
            },
        )
    ]


def test_moving_stock_needs_its_own_permission():
    coffee = create("Coffee", initial_stock="10")
    editor = ctx_with("inventory.view_product", "inventory.change_product")
    refused(
        PermissionDenied,
        lambda: get("inventory.stock.count")(
            editor, CountIn(product_id=coffee.id, stock="5", reason="count")
        ),
    )
    refused(PermissionDenied, lambda: receive((coffee.id, "1"), role="hub_employee"))
    counter = ctx_with("inventory.adjust_stock")
    assert get("inventory.stock.count")(
        counter, CountIn(product_id=coffee.id, stock="5", reason="recount")
    ).stock == Decimal("5")


# inventory.stock.count (INVENTORY-F14)


def test_a_count_is_absolute_and_the_ledger_keeps_the_difference_and_the_reason():
    coffee = create("Coffee", initial_stock="10")
    clear_outbox()

    assert count(coffee.id, "7", "weekly count: shrinkage").stock == Decimal("7")

    movement = StockMovement.objects.get(movement_type="count")
    assert (movement.qty, movement.stock_after, movement.reason) == (
        Decimal("-3"),
        Decimal("7"),
        "weekly count: shrinkage",
    )
    assert outbox() == [
        (
            events.STOCK_CHANGED,
            {
                "product_id": str(coffee.id),
                "movement_type": "count",
                "qty": "-3.000",
                "stock_after": "7.000",
            },
        )
    ]


def test_a_count_without_difference_writes_nothing():
    coffee = create("Coffee", initial_stock="7")
    clear_outbox()
    count(coffee.id, "7", "recount, no change")
    assert movements(coffee.id, "count") == [] and outbox() == []


def test_a_count_applies_to_an_article_without_stock_control_and_never_crosses():
    created = create(track_stock=False, initial_stock="10", low_stock_threshold="5")
    count(created.id, "1")
    assert stock_of(created.id) == Decimal("1")
    assert events.STOCK_THRESHOLD_CROSSED not in event_names()


def test_a_count_crosses_the_threshold_in_either_direction():
    created = create(initial_stock="10", low_stock_threshold="5")
    count(created.id, "3")
    count(created.id, "4")  # still below: silence
    count(created.id, "8")
    crossings = [
        (payload["crossing"], payload["movement_type"])
        for _, payload in outbox(events.STOCK_THRESHOLD_CROSSED)
    ]
    assert crossings == [("below", "count"), ("recovered", "count")]


def test_a_service_is_not_counted_and_an_off_grid_count_is_refused():
    cut = create("Cut", product_type="service")
    error = refused(Conflict, lambda: count(cut.id, "1"))
    assert (error.code, error.message) == (
        "inventory.service_has_no_stock",
        "A service has no stock.",
    )
    coffee = create("Coffee")
    assert (
        refused(Conflict, lambda: count(coffee.id, "1.5")).code
        == "inventory.off_grid_quantity"
    )


def test_counting_a_missing_product_is_not_found():
    error = refused(NotFound, lambda: count(uuid.uuid7(), "1"))
    assert error.message == "This product does not exist in this hub."


# inventory.stock.write_off (INVENTORY-F15)


def test_a_write_off_lowers_the_stock_with_its_reason():
    wine = create("Wine", "WIN", initial_stock="10", low_stock_threshold="9")
    clear_outbox()

    assert write_off(wine.id, "2", "broken bottles").stock == Decimal("8")

    movement = StockMovement.objects.get(movement_type="write_off")
    assert (movement.qty, movement.stock_after, movement.reason) == (
        Decimal("-2"),
        Decimal("8"),
        "broken bottles",
    )
    assert event_names() == [events.STOCK_CHANGED, events.STOCK_THRESHOLD_CROSSED]
    assert outbox(events.STOCK_THRESHOLD_CROSSED)[0][1]["crossing"] == "below"


def test_without_selling_without_stock_a_write_off_beyond_the_balance_is_refused():
    wine = create("Wine", initial_stock="3")
    clear_outbox()
    error = refused(Conflict, lambda: write_off(wine.id, "9"))
    assert (error.code, error.message) == (
        "inventory.insufficient_stock",
        "There is not enough stock to complete the operation.",
    )
    assert (
        stock_of(wine.id) == Decimal("3")
        and movements(wine.id, "write_off") == []
        and outbox() == []
    )


def test_selling_without_stock_lets_the_balance_go_negative():
    configure(allow_sell_without_stock=True)
    wine = create("Wine", initial_stock="5")
    assert write_off(wine.id, "8").stock == Decimal("-3")


@pytest.mark.parametrize("kind", ["untracked", "business_off"])
def test_a_write_off_of_an_article_without_stock_control_is_refused_and_says_why(kind):
    # The screen offers it only to articles that track stock; by the assistant or the API a write-off
    # that would do nothing is not a silent success either (2026-10-14).
    if kind == "business_off":
        configure(track_stock=False)
    created = create(initial_stock="5", track_stock=False if kind == "untracked" else None)
    clear_outbox()
    error = refused(Conflict, lambda: write_off(created.id, "1"))
    message = "This article does not track its stock: there is nothing to write off."
    assert (error.code, error.message, error.fields) == ("inventory.stock_not_tracked", message, {"qty": message})
    assert stock_of(created.id) == Decimal("5") and movements(created.id, "write_off") == [] and outbox() == []


def test_a_write_off_of_a_service_is_refused_as_a_service_has_no_stock():
    massage = create(product_type="service")
    clear_outbox()
    error = refused(Conflict, lambda: write_off(massage.id, "1"))
    assert (error.code, error.fields) == ("inventory.service_has_no_stock", {"product_id": "A service has no stock."})
    assert movements(massage.id, "write_off") == [] and outbox() == []


def test_a_write_off_of_half_a_gram_on_a_gram_step_is_refused():
    gambas = create("Gambas", unit="g", initial_stock="10")
    error = refused(Conflict, lambda: write_off(gambas.id, "0.5"))
    assert error.code == "inventory.off_grid_quantity"
    assert stock_of(gambas.id) == Decimal("10")


def test_writing_off_a_missing_product_is_not_found():
    refused(NotFound, lambda: write_off(uuid.uuid7(), "1"))


# inventory.config.update (INVENTORY-F19)


def test_settings_are_saved_once_and_changed_by_parts():
    assert configure(track_stock=False).model_dump() == {
        "allow_sell_without_stock": False,
        "low_stock_threshold": 10,
        "track_stock": False,
    }
    assert configure(low_stock_threshold=3).model_dump() == {
        "allow_sell_without_stock": False,
        "low_stock_threshold": 3,
        "track_stock": False,
    }
    assert (
        Settings.objects.count() == 1 and Settings.objects.get().updated_by == "tester"
    )
    assert event_names() == [events.CONFIG_UPDATED, events.CONFIG_UPDATED]
    clear_outbox()
    configure(low_stock_threshold=3)
    assert outbox() == []


def test_changing_the_default_threshold_does_not_touch_existing_products():
    created = create()
    configure(low_stock_threshold=40)
    assert Product.objects.get(pk=created.id).low_stock_threshold == Decimal("10")


def test_the_employee_cannot_change_the_settings():
    refused(
        PermissionDenied,
        lambda: run(
            "inventory.config.update", ConfigPatchIn(track_stock=False), "hub_employee"
        ),
    )


# inventory.stock.apply_sale (INVENTORY-F21, F22, F18)


def test_a_completed_sale_lowers_each_line_with_the_sale_as_reference():
    coffee, gambas = (
        create("Coffee", initial_stock="10"),
        create("Gambas", unit="kg", initial_stock="2.5"),
    )
    sale = uuid.uuid7()
    clear_outbox()

    result = sell(sale, line(coffee.id, "3"), line(gambas.id, "0.5"))

    assert result == SaleStockOut(
        sale_id=sale, state="moved", applied=True, movements=2
    )
    assert (stock_of(coffee.id), stock_of(gambas.id)) == (Decimal("7"), Decimal("2"))
    movement = StockMovement.objects.get(product_id=gambas.id, movement_type="sale")
    assert (movement.qty, movement.stock_after, movement.reference, movement.actor) == (
        Decimal("-0.5"),
        Decimal("2"),
        str(sale),
        "system",
    )
    assert event_names() == [events.STOCK_CHANGED, events.STOCK_CHANGED]
    assert SaleStock.objects.get().state == "moved"


def test_the_same_article_on_several_lines_leaves_a_movement_per_line_and_crosses_once():
    coffee = create("Coffee", initial_stock="10", low_stock_threshold="5")
    menu = line(None, "1", components=[{"product_id": coffee.id, "quantity": "2"}])
    clear_outbox()

    sell(uuid.uuid7(), line(coffee.id, "2"), menu, line(coffee.id, "2"))

    assert [qty for _, qty, _ in movements(coffee.id, "sale")] == [
        Decimal("-2"),
        Decimal("-2"),
        Decimal("-2"),
    ]
    [(_, crossing)] = outbox(events.STOCK_THRESHOLD_CROSSED)
    assert (
        crossing["previous_quantity"],
        crossing["current_quantity"],
        crossing["crossing"],
        crossing["movement_type"],
    ) == (
        "10.000",
        "4.000",
        "below",
        "sale",
    )


def test_a_menu_lowers_its_components_and_never_itself():
    first, drink = (
        create("First", initial_stock="10"),
        create("Drink", initial_stock="10"),
    )
    menu_id = uuid.uuid7()  # the combo is not an article of the catalog
    sell(
        uuid.uuid7(),
        {
            "product_id": menu_id,
            "quantity": "3",
            "components": [
                {"product_id": first.id, "quantity": "3"},
                {"product_id": drink.id, "quantity": "3"},
            ],
        },
    )
    assert (stock_of(first.id), stock_of(drink.id)) == (Decimal("7"), Decimal("7"))
    assert StockMovement.objects.filter(movement_type="sale").count() == 2


def test_services_free_price_lines_and_articles_without_stock_control_move_nothing():
    cut = create("Cut", product_type="service")
    loose = create("Napkin", initial_stock="10", track_stock=False)
    drink = create("Drink", initial_stock="10")
    pack = line(
        None,
        "1",
        components=[
            {"product_id": cut.id, "quantity": "1", "is_service": True},
            {"product_id": drink.id, "quantity": "1"},
        ],
    )

    result = sell(
        uuid.uuid7(),
        line(cut.id, "1", is_service=True),
        line(None, "1"),
        line(loose.id, "2"),
        pack,
    )

    assert (result.movements, stock_of(loose.id), stock_of(drink.id)) == (
        1,
        Decimal("10"),
        Decimal("9"),
    )


def test_the_business_does_not_track_but_the_article_opts_in():
    configure(track_stock=False)
    opted_in, inherits = (
        create("In", initial_stock="10", track_stock=True),
        create("Inherits", initial_stock="10"),
    )
    sell(uuid.uuid7(), line(opted_in.id, "2"), line(inherits.id, "2"))
    assert (stock_of(opted_in.id), stock_of(inherits.id)) == (
        Decimal("8"),
        Decimal("10"),
    )


def test_without_selling_without_stock_an_article_that_does_not_reach_lowers_nothing():
    scarce, plenty = (
        create("Scarce", initial_stock="1"),
        create("Plenty", initial_stock="10"),
    )
    result = sell(uuid.uuid7(), line(scarce.id, "2"), line(plenty.id, "2"))
    assert (stock_of(scarce.id), stock_of(plenty.id), result.movements) == (
        Decimal("1"),
        Decimal("8"),
        1,
    )
    assert movements(scarce.id, "sale") == []


def test_selling_without_stock_goes_negative():
    configure(allow_sell_without_stock=True)
    scarce = create("Scarce", initial_stock="1")
    sell(uuid.uuid7(), line(scarce.id, "3"))
    assert stock_of(scarce.id) == Decimal("-2")


def test_a_sale_that_moves_nothing_is_noted_so_that_its_void_restores_nothing():
    created = create("Coffee", initial_stock="8", track_stock=False)
    sale = uuid.uuid7()
    clear_outbox()
    assert sell(sale, line(created.id, "2")) == SaleStockOut(
        sale_id=sale, state="unmoved", applied=True, movements=0
    )
    assert outbox() == []
    assert void(sale).movements == 0 and stock_of(created.id) == Decimal("8")


def test_a_sale_delivered_twice_lowers_once():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(coffee.id, "3"))
    again = sell(sale, line(coffee.id, "3"))
    assert (again.applied, again.state, stock_of(coffee.id)) == (
        False,
        "moved",
        Decimal("7"),
    )


def test_unknown_and_deleted_products_of_a_sale_are_skipped():
    gone = create("Gone", initial_stock="5")
    run("inventory.product.delete", ProductRefIn(id=gone.id))
    result = sell(uuid.uuid7(), line(uuid.uuid7(), "1"), line(gone.id, "1"))
    assert (result.state, stock_of(gone.id)) == ("unmoved", Decimal("5"))


# inventory.stock.restore_sale (INVENTORY-F23)


def test_a_void_restores_exactly_what_the_sale_lowered():
    coffee = create("Coffee", initial_stock="10", low_stock_threshold="8")
    gambas = create("Gambas", unit="kg", initial_stock="10")
    scarce = create("Scarce", initial_stock="1")
    sale = uuid.uuid7()
    sell(
        sale,
        line(coffee.id, "1"),
        line(coffee.id, "2"),
        line(gambas.id, "2.5"),
        line(scarce.id, "5"),
    )
    clear_outbox()

    result = void(sale)

    assert result == SaleStockOut(
        sale_id=sale, state="voided", applied=True, movements=2
    )
    assert (stock_of(coffee.id), stock_of(gambas.id), stock_of(scarce.id)) == (
        Decimal("10"),
        Decimal("10"),
        Decimal("1"),
    )
    assert movements(coffee.id, "void") == [("void", Decimal("3"), Decimal("10"))]
    assert StockMovement.objects.get(
        product_id=gambas.id, movement_type="void"
    ).reference == str(sale)
    assert event_names() == [
        events.STOCK_CHANGED,
        events.STOCK_THRESHOLD_CROSSED,
        events.STOCK_CHANGED,
    ]
    assert outbox(events.STOCK_THRESHOLD_CROSSED)[0][1]["crossing"] == "recovered"


def test_a_void_delivered_twice_restores_once():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(coffee.id, "3"))
    void(sale)
    assert void(sale).applied is False
    assert stock_of(coffee.id) == Decimal("10")


def test_a_void_that_arrives_before_its_sale_leaves_the_stock_as_it_was():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    assert void(sale) == SaleStockOut(
        sale_id=sale, state="voided", applied=True, movements=0
    )
    assert sell(sale, line(coffee.id, "3")).applied is False
    assert stock_of(coffee.id) == Decimal("10") and movements(coffee.id, "sale") == []


def test_a_void_restores_even_if_the_article_stopped_tracking_stock_in_between():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(coffee.id, "4"))
    update(coffee.id, track_stock=False)
    void(sale)
    assert stock_of(coffee.id) == Decimal("10")


def test_an_article_deleted_after_the_sale_gets_nothing_back():
    coffee = create("Coffee", initial_stock="10")
    sale = uuid.uuid7()
    sell(sale, line(coffee.id, "4"))
    run("inventory.product.delete", ProductRefIn(id=coffee.id))
    assert void(sale).movements == 0
    assert stock_of(coffee.id) == Decimal("6")


# Notifications: after the COMMIT, on the channel of the command's scope only


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=1.0, stop_after=None):
    return [
        json.loads(note.payload)
        for note in session.notifies(timeout=timeout, stop_after=stop_after)
    ]


@pytest.mark.django_db(transaction=True)
def test_a_write_in_scope_b_notifies_b_only(listen):
    TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})
    on_a, on_b = listen(A), listen(B)

    get("inventory.product.create")(
        ctx_for("hub_admin", B),
        ProductIn(
            name="Coffee", sku="CAF", price=1, tax_category_key=TAX, initial_stock="1"
        ),
    )

    assert received(on_b, stop_after=1) == [
        {"events": [events.PRODUCT_CREATED, events.STOCK_CHANGED]}
    ]
    assert received(on_a, timeout=0.3) == []


# Named as a person says it (assistant, voice): the SKU or the name instead of the id


def test_every_action_on_a_product_takes_its_sku_or_its_name():
    wine = create("Red wine", "WIN-R", initial_stock="10")
    drinks = run("inventory.category.create", CategoryIn(name="Drinks"))

    assert run("inventory.product.update", ProductPatchIn(product="win-r", price=900)).price == 900
    assert write_off(None, "2", "broken bottles", said="red wine").stock == Decimal("8")
    assert count(None, "7", "weekly count", said="Red wine").stock == Decimal("7")
    [after] = run("inventory.stock.receive", ReceiveIn(items=[{"product": "WIN-R", "qty": "3"}])).rows
    assert after.stock == Decimal("10")
    link = ProductCategoryIn(product="red wine", category="drinks")
    assert run("inventory.product_category.add", link).changed is True
    assert run("inventory.product.get", ProductRefIn(product="red wine")).category_ids == [drinks.id]
    assert run("inventory.product.delete", ProductRefIn(product="WIN-R")) == DeletedOut(id=wine.id)


def test_a_category_is_changed_and_deleted_by_its_name():
    drinks = run("inventory.category.create", CategoryIn(name="Drinks"))
    assert run("inventory.category.update", CategoryPatchIn(category="drinks", name="Beverages")).name == "Beverages"
    assert run("inventory.category.delete", CategoryRefIn(category="Beverages")) == DeletedOut(id=drinks.id)


def test_a_name_that_matches_several_products_asks_which_one():
    create("Red wine", "WIN-R")
    create("White wine", "WIN-W")
    error = refused(Conflict, lambda: write_off(None, "1", "broken", said="wine"))
    assert error.code == "inventory.product_ambiguous"


def test_a_reception_line_with_a_product_nobody_has_says_which_line():
    coffee = create("Coffee")
    error = refused(InvalidPayload, lambda: run("inventory.stock.receive", ReceiveIn(items=[{"product_id": coffee.id, "qty": 1}, {"product": "beer", "qty": 1}])))
    assert list(error.fields) == ["items.1.product"]
    assert stock_of(coffee.id) == 0


def test_a_deactivated_tax_category_is_refused_as_if_it_did_not_exist():
    TaxCategory.objects.create(key="test.old", name="Old", is_active=False)
    error = refused(InvalidPayload, lambda: create(tax_category_key="test.old"))
    assert list(error.fields) == ["tax_category_key"]


def test_an_imported_category_name_or_slug_too_long_fails_its_row_and_is_never_cut():
    report = import_categories({"name": "x" * 101}, {"name": "Food", "slug": "y" * 121}, {"name": "Bebidas Frías", "slug": "Bebidas Frías"})
    assert [(row.status, row.reason) for row in report.rows] == [
        ("failed", "A text is longer than its column allows"),
        ("failed", "A text is longer than its column allows"),
        ("created", ""),
    ]
    assert Category.objects.get().slug == "bebidas-frias"  # a slug cell is normalized like a typed one


def test_an_import_takes_back_the_apostrophe_the_export_puts_in_front_of_a_formula():
    import_products(row("'@SUM(A1)", name="'=HYPERLINK(1)", description="'+cmd"))
    import_categories({"name": "'-Drinks"})
    product = Product.objects.get()
    assert (product.name, product.sku, product.description) == ("=HYPERLINK(1)", "@SUM(A1)", "+cmd")
    assert Category.objects.get().name == "-Drinks"


def test_an_amount_or_a_quantity_too_large_fails_its_row_and_the_rehearsal_says_the_same():
    rows = (
        row("P", price="99999999999999999999"),
        row("C", cost="100000000000000"),
        row("S", stock="9999999999999"),  # 13 whole digits
        row("T", low_stock_threshold="1000000000000"),
        row("OK", stock="999999999999"),  # 12 whole digits: the most a quantity holds
    )
    refusals = [
        ("P", "failed", "Price or cost too large"),
        ("C", "failed", "Price or cost too large"),
        ("S", "failed", "Quantity too large"),
        ("T", "failed", "Quantity too large"),
    ]

    rehearsal = import_products(*rows, dry_run=True)
    real = import_products(*rows)

    assert [(row.key, row.status, row.reason) for row in rehearsal.rows] == [*refusals, ("OK", "ready", "")]
    assert [(row.key, row.status, row.reason) for row in real.rows] == [*refusals, ("OK", "created", "")]
    assert stock_of(Product.objects.get().id) == Decimal("999999999999")


EXPORT_FIELDS = {
    "Name": "name",
    "SKU": "sku",
    "Price": "price",
    "Cost": "cost",
    "Stock": "stock",
    "Threshold": "low_stock_threshold",
    "EAN-13": "ean13",
    "Description": "description",
    "Unit": "unit",
    "Tax category": "tax_category_key",
}


def exported_rows():
    """The product export read back as the import's rows (its headers are the import's)."""
    import csv
    import io

    from apps.inventory.schemas import ProductFiltersIn

    content = run("inventory.product.export", ProductFiltersIn()).content.lstrip("﻿")
    return [
        {field: cells[header] for header, field in EXPORT_FIELDS.items()} for cells in csv.DictReader(io.StringIO(content))
    ]


def test_the_catalog_exported_and_imported_again_is_skipped_untouched_even_with_a_negative_stock():
    # INVENTORY-F11: the export imports back without changes; F09: a live SKU is skipped, whatever its cells.
    configure(allow_sell_without_stock=True)
    wine = create("Wine", "WIN", initial_stock="5")
    write_off(wine.id, "8")  # -3: sold without stock
    create("=Gambas", "GAM", unit="kg", initial_stock="2.5", ean13="8412345678905", price=1250)
    rows = exported_rows()
    clear_outbox()

    report = import_products(*rows)

    assert (report.total, report.skipped, report.failed, report.created) == (2, 2, 0, 0)
    assert outbox() == [] and stock_of(wine.id) == Decimal("-3")


def test_an_exported_catalog_imports_into_an_empty_one_as_it_was():
    create("=Gambas", "GAM", unit="kg", initial_stock="2.5", ean13="8412345678905", price=1250, cost=820)
    rows = exported_rows()
    run("inventory.product.delete", ProductRefIn(product="GAM"))

    assert import_products(*rows).created == 1
    again = Product.objects.get(is_deleted=False)
    assert (again.name, again.price, again.cost, again.stock, again.unit, again.ean13) == (
        "=Gambas",
        1250,
        820,
        Decimal("2.5"),
        "kg",
        "8412345678905",
    )


# The edges of the threshold and of the exact balance (INVENTORY-F18, F15, F21)


def crossings():
    return [(payload["crossing"], payload["movement_type"]) for _, payload in outbox(events.STOCK_THRESHOLD_CROSSED)]


def test_going_down_to_exactly_the_threshold_is_below_and_coming_back_up_to_it_is_not_recovered():
    created = create(initial_stock="10", low_stock_threshold="5")
    count(created.id, "5")  # 10 → 5: at the threshold is low
    count(created.id, "4")
    count(created.id, "5")  # 4 → 5: still at it, not recovered
    assert crossings() == [("below", "count")]


def test_one_above_the_threshold_is_recovered():
    created = create(initial_stock="5", low_stock_threshold="5")
    receive((created.id, "1"))  # 5 → 6
    assert crossings() == [("recovered", "reception")]


def test_without_selling_without_stock_exactly_the_balance_can_still_go():
    sold, written_off = create("Sold", initial_stock="3"), create("Written off", initial_stock="2")

    assert sell(uuid.uuid7(), line(sold.id, "3")).movements == 1
    assert write_off(written_off.id, "2").stock == Decimal("0")

    assert movements(sold.id, "sale") == [("sale", Decimal("-3"), Decimal("0"))]
    assert movements(written_off.id, "write_off") == [("write_off", Decimal("-2"), Decimal("0"))]


# Two writes at the same instant: the second waits for the first's rows, then sees what it left


QUIET_JOIN = 0.3


def _in_thread(target):
    outcome = {}

    def body():
        try:
            outcome["result"] = target()
        except Exception as error:  # the outcome is asserted by the test
            outcome["error"] = error
        finally:
            connection.close()

    thread = threading.Thread(target=body)
    thread.start()
    return thread, outcome


def _first_holds(write):
    """Run ``write`` in a thread inside a transaction kept open (its locks held) until released."""
    done, release = threading.Event(), threading.Event()

    def first():
        with transaction.atomic():
            result = write()
            done.set()
            release.wait(5)
        return result

    holder, held = _in_thread(first)
    assert done.wait(5)
    return holder, held, release


def _then(holder, release, second):
    second.join(QUIET_JOIN)
    waited = second.is_alive()  # it waits for the first one, it does not read what it had not written
    release.set()
    holder.join(5)
    second.join(5)
    return waited


@pytest.mark.django_db(transaction=True)
def test_two_sales_of_the_last_unit_at_once_lower_it_once():
    last = create("Last", initial_stock="1")
    holder, held, release = _first_holds(lambda: sell(uuid.uuid7(), line(last.id, "1")))

    second, outcome = _in_thread(lambda: sell(uuid.uuid7(), line(last.id, "1")))

    assert _then(holder, release, second)
    assert (held["result"].movements, outcome["result"].movements) == (1, 0)
    assert stock_of(last.id) == Decimal("0")
    assert len(movements(last.id, "sale")) == 1


@pytest.mark.django_db(transaction=True)
def test_the_same_sale_delivered_twice_at_once_lowers_once():
    coffee, sale = create("Coffee", initial_stock="10"), uuid.uuid7()
    holder, held, release = _first_holds(lambda: sell(sale, line(coffee.id, "3")))

    second, outcome = _in_thread(lambda: sell(sale, line(coffee.id, "3")))

    assert _then(holder, release, second)
    assert (held["result"].applied, outcome["result"].applied) == (True, False)
    assert stock_of(coffee.id) == Decimal("7")
    assert len(movements(coffee.id, "sale")) == 1


@pytest.mark.django_db(transaction=True)
def test_a_sale_and_its_void_at_once_leave_the_stock_as_it_was():
    coffee, sale = create("Coffee", initial_stock="10"), uuid.uuid7()
    holder, held, release = _first_holds(lambda: sell(sale, line(coffee.id, "3")))

    second, outcome = _in_thread(lambda: void(sale))

    assert _then(holder, release, second)
    assert (held["result"].movements, outcome["result"].movements) == (1, 1)
    assert stock_of(coffee.id) == Decimal("10")
    assert [movement_type for movement_type, _, _ in movements(coffee.id)] == ["initial", "sale", "void"]


@pytest.mark.django_db(transaction=True)
def test_two_write_offs_of_the_whole_balance_at_once_take_it_once():
    wine = create("Wine", initial_stock="2")
    holder, held, release = _first_holds(lambda: write_off(wine.id, "2"))

    second, outcome = _in_thread(lambda: write_off(wine.id, "2"))

    assert _then(holder, release, second)
    assert held["result"].stock == Decimal("0")
    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "inventory.insufficient_stock"
    assert stock_of(wine.id) == Decimal("0")
    assert len(movements(wine.id, "write_off")) == 1
