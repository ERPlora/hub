"""Write operations of the inventory app: one transaction each, with its events in the outbox.

Cases from the WORKBOOK and from the old module's batteries (ledger, stock, listeners, track_stock,
combo stock, products, category_delete, deleted_product_frees_its_code, units). Here are the declarations, the helpers
the other files share, the sold-out switch, the links of a product and a category, the settings, the notifications,
what a person names aloud, the edges of the threshold and two writes at once; each other module of ``services/`` has
its own ``test_services_<module>.py``.
"""

import json
import threading
import uuid
from decimal import Decimal

import psycopg
import pytest
from live.context import system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent
from live.operations import atomic, get
from live.outbox import channel_for

from apps.inventory import events
from apps.inventory.models import (
    Category,
    Product,
    SaleStock,
    Settings,
    StockMovement,
)
from apps.inventory.schemas.categories import CategoryIn, CategoryOut, CategoryPatchIn
from apps.inventory.schemas.fields import CategoryRefIn, DeletedOut, ProductRefIn
from apps.inventory.schemas.imports import CategoryImportIn, ImportReportOut, ProductImportIn
from apps.inventory.schemas.product_categories import ProductCategoryIn, ProductCategoryLinkOut
from apps.inventory.schemas.products import ProductIn, ProductOut, ProductPatchIn, ProductSoldOutIn, ProductsOut
from apps.inventory.schemas.sale_reactions import SaleCompletedIn, SaleStockOut, SaleVoidedIn
from apps.inventory.schemas.settings import ConfigOut, ConfigPatchIn
from apps.inventory.schemas.stock import CountIn, ReceiveIn, WriteOffIn
from apps.tax.models import TaxCategory
from base.tenancy.context import use_hub
from base.tenancy.tests.concurrency import in_a_thread

from .conftest import A, B, HUB_DB, HUB_DB_COMMITTED, ctx_for
from .test_apps import CHECKS

pytestmark = HUB_DB

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
        ("inventory.product.set_sold_out", "inventory.change_product", ProductSoldOutIn, ProductOut, "normal"),
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
    # An import's card says its rows by their names and the tax categories they take (import_card); a new product's
    # puts first its name, its price and the VAT it charges (card_order).
    summary = {"summary"} if input in (ProductImportIn, CategoryImportIn, ProductIn) else set()
    # A write that names a product or a category checks it before its card (hub#2295).
    check = {"check"} if name in CHECKS else set()
    assert set(op.ai) == {"description", "risk", "asks", *summary, *check} and op.ai["description"]
    assert op.ai.get("check") == CHECKS.get(name)
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


# inventory.product.set_sold_out (INVENTORY-F29)


def sold_out(product_id=None, value=True, role="hub_admin", said=None):
    return run(
        "inventory.product.set_sold_out",
        ProductSoldOutIn(id=product_id, product=said, sold_out=value),
        role,
    )


def test_a_new_product_is_on_sale():
    assert create().is_sold_out is False
    assert Product.objects.get().is_sold_out is False


def test_mark_a_product_sold_out_and_put_it_back_on_sale():
    created = create("Croquettes", "CRO-1")
    clear_outbox()

    marked = sold_out(created.id)

    # Sold out is not inactive: the switch stays on, the till stops offering it (INVENTORY-F27).
    assert (marked.is_sold_out, marked.is_active) == (True, True)
    assert Product.objects.get().updated_by == "tester"
    [(name, payload)] = outbox()
    assert (name, payload["id"], payload["is_sold_out"], payload["is_active"]) == (
        events.PRODUCT_UPDATED,
        str(created.id),
        True,
        True,
    )

    clear_outbox()
    assert sold_out(created.id, False).is_sold_out is False
    assert [(name, payload["is_sold_out"]) for name, payload in outbox()] == [
        (events.PRODUCT_UPDATED, False)
    ]


def test_a_product_is_named_by_its_sku_or_by_its_name_as_said_aloud():
    created = create("Croquettes", "CRO-1")
    assert sold_out(said="croquettes").id == created.id
    assert sold_out(said="cro-1", value=False).is_sold_out is False


def test_marking_what_it_already_is_records_nothing():
    created = create()
    sold_out(created.id)
    clear_outbox()
    assert sold_out(created.id).is_sold_out is True
    assert outbox() == []


def test_an_edit_or_the_switch_keeps_it_sold_out():
    created = create()
    sold_out(created.id)
    update(created.id, name="Espresso", is_active=False)
    assert update(created.id, is_active=True).is_sold_out is True


def test_an_employee_cannot_mark_a_product_sold_out():
    created = create()
    refused(PermissionDenied, lambda: sold_out(created.id, role="hub_employee"))
    assert Product.objects.get().is_sold_out is False


@pytest.mark.parametrize("deleted", [True, False])
def test_marking_a_missing_or_deleted_product_is_not_found(deleted):
    target = create().id if deleted else uuid.uuid7()
    if deleted:
        run("inventory.product.delete", ProductRefIn(id=target))
    refused(NotFound, lambda: sold_out(target))


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


@HUB_DB_COMMITTED
def test_a_write_in_scope_b_notifies_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)
    with use_hub(hub_b):
        TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})
        get("inventory.product.create")(
            ctx_for("hub_admin", B), ProductIn(name="Coffee", sku="CAF", price=1, tax_category_key=TAX, initial_stock="1")
        )

    assert received(on_b, stop_after=1) == [
        {"events": [events.PRODUCT_CREATED, events.STOCK_CHANGED]}
    ]
    assert received(on_a, timeout=0.3) == []


@HUB_DB_COMMITTED
def test_marking_a_product_sold_out_in_scope_b_notifies_b_only(listen, hub_b):
    with use_hub(hub_b):
        TaxCategory.objects.get_or_create(key=TAX, defaults={"name": "General"})
        croquettes = get("inventory.product.create")(
            ctx_for("hub_admin", B), ProductIn(name="Croquettes", sku="CRO", price=1, tax_category_key=TAX)
        )
        on_a, on_b = listen(A), listen(B)
        get("inventory.product.set_sold_out")(ctx_for("hub_admin", B), ProductSoldOutIn(id=croquettes.id, sold_out=True))

    # The till's catalog of B re-runs on this event (live.py); the one of A hears nothing.
    assert received(on_b, stop_after=1) == [{"events": [events.PRODUCT_UPDATED]}]
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
    """Runs ``target`` in its own thread and session of the business at work; its outcome under result or error."""
    outcome = {}

    def body():
        try:
            outcome["result"] = target()
        except Exception as error:  # the outcome is asserted by the test
            outcome["error"] = error

    thread = in_a_thread(body, [None])
    thread.start()
    return thread, outcome


def _first_holds(write):
    """Run ``write`` in a thread inside a transaction kept open (its locks held) until released."""
    done, release = threading.Event(), threading.Event()

    def first():
        with atomic():
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


def test_inventory_f16_a_sale_keeps_the_number_it_arrived_with_even_one_too_long_for_the_ledger():
    coffee = create("Coffee", initial_stock="5")
    sold, long = uuid.uuid7(), uuid.uuid7()

    system("inventory.stock.apply_sale", SaleCompletedIn(sale_id=sold, sale_number="20261021-0099", items=[line(coffee.id, "1")]))
    system("inventory.stock.apply_sale", SaleCompletedIn(sale_id=long, sale_number="X" * 40, items=[line(coffee.id, "1")]))

    # Sales does not know these sales (they never went through it): no ticket number, and no failure.
    assert (SaleStock.objects.get(sale_id=sold).sale_number, SaleStock.objects.get(sale_id=sold).document_number) == (
        "20261021-0099",
        "",
    )
    assert SaleStock.objects.get(sale_id=long).sale_number == "X" * 24
    assert stock_of(coffee.id) == Decimal("3")


@HUB_DB_COMMITTED
def test_two_sales_of_the_last_unit_at_once_lower_it_once(plan_with_room):
    last = create("Last", initial_stock="1")
    holder, held, release = _first_holds(lambda: sell(uuid.uuid7(), line(last.id, "1")))

    second, outcome = _in_thread(lambda: sell(uuid.uuid7(), line(last.id, "1")))

    assert _then(holder, release, second)
    assert (held["result"].movements, outcome["result"].movements) == (1, 0)
    assert stock_of(last.id) == Decimal("0")
    assert len(movements(last.id, "sale")) == 1


@HUB_DB_COMMITTED
@pytest.mark.parametrize(
    ("start", "crosses_on"),
    [
        ("11", "the first"),  # each alone would cross: said once, not twice
        ("12", "the second"),  # neither alone would cross from the balance it started with: never lost
    ],
)
def test_inventory_f18_two_sales_at_once_say_the_crossing_exactly_once(start, crosses_on, plan_with_room):
    article = create("Article", initial_stock=start, low_stock_threshold="10")
    holder, held, release = _first_holds(lambda: sell(uuid.uuid7(), line(article.id, "1")))

    second, outcome = _in_thread(lambda: sell(uuid.uuid7(), line(article.id, "1")))

    assert _then(holder, release, second)
    assert (held["result"].movements, outcome["result"].movements) == (1, 1)
    assert stock_of(article.id) == Decimal(start) - 2
    said = [
        (row.payload["crossing"], row.payload["previous_quantity"], row.payload["current_quantity"])
        for row in OutboxEvent.objects.filter(name=events.STOCK_THRESHOLD_CROSSED)
    ]
    assert said == [("below", "11.000", "10.000")], crosses_on


@HUB_DB_COMMITTED
def test_the_same_sale_delivered_twice_at_once_lowers_once(plan_with_room):
    coffee, sale = create("Coffee", initial_stock="10"), uuid.uuid7()
    holder, held, release = _first_holds(lambda: sell(sale, line(coffee.id, "3")))

    second, outcome = _in_thread(lambda: sell(sale, line(coffee.id, "3")))

    assert _then(holder, release, second)
    assert (held["result"].applied, outcome["result"].applied) == (True, False)
    assert stock_of(coffee.id) == Decimal("7")
    assert len(movements(coffee.id, "sale")) == 1


@HUB_DB_COMMITTED
def test_a_sale_and_its_void_at_once_leave_the_stock_as_it_was(plan_with_room):
    coffee, sale = create("Coffee", initial_stock="10"), uuid.uuid7()
    holder, held, release = _first_holds(lambda: sell(sale, line(coffee.id, "3")))

    second, outcome = _in_thread(lambda: void(sale))

    assert _then(holder, release, second)
    assert (held["result"].movements, outcome["result"].movements) == (1, 1)
    assert stock_of(coffee.id) == Decimal("10")
    assert [movement_type for movement_type, _, _ in movements(coffee.id)] == ["initial", "sale", "void"]


@HUB_DB_COMMITTED
def test_two_write_offs_of_the_whole_balance_at_once_take_it_once(plan_with_room):
    wine = create("Wine", initial_stock="2")
    holder, held, release = _first_holds(lambda: write_off(wine.id, "2"))

    second, outcome = _in_thread(lambda: write_off(wine.id, "2"))

    assert _then(holder, release, second)
    assert held["result"].stock == Decimal("0")
    assert isinstance(outcome.get("error"), Conflict) and outcome["error"].code == "inventory.insufficient_stock"
    assert stock_of(wine.id) == Decimal("0")
    assert len(movements(wine.id, "write_off")) == 1
