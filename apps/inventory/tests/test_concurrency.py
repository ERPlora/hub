"""A product, a category or a tax category deleted while inventory reads or writes it: real sessions in threads.

The detail found the product and then loaded it again by its id, so a deletion committed between the two
reads handed ``None`` to the output (a 500). A read that a deletion lands in the middle of answers what it
read or 404, never a 500.

The writes that name a category (putting a product in it, creating or editing a product with it) or a tax
category (a product or a category created, edited or imported with it) read it unheld: a deletion committed
between that read and the write either left a product hanging from a deleted category or, the Hub admin's,
made the database refuse the write at its INSERT (a 500). A write holds what it names, so the deletion waits
for it; one already under way when the write reads it is not found, as one deleted before. Both the business's
«Delete» (the row stays, marked deleted) and the Hub admin's (the row goes) are landed there.
"""

import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from live.errors import NotFound, OperationError
from live.operations import get

from apps.inventory.models import Category, Product, ProductCategory
from apps.inventory.schemas import (
    CategoryImportIn,
    CategoryIn,
    CategoryPatchIn,
    CategoryRefIn,
    ProductCategoryIn,
    ProductImportIn,
    ProductIn,
    ProductPatchIn,
    ProductRefIn,
)
from apps.tax.models import TaxCategory

from .conftest import ctx_for

pytestmark = pytest.mark.django_db(transaction=True)

DELETIONS = ["operation", "row"]
#: A deletion gives up after this on a row another session holds (a real one waits for its COMMIT).
LOCK_TIMEOUT = "300ms"
#: Postgres' ``lock_not_available``: the deletion found the row held.
LOCK_NOT_AVAILABLE = "55P03"
#: How long a deletion under way holds its row before it commits.
IN_FLIGHT = 0.5
GENERAL, PROBE = "product.general", "product.probe"
#: The business's «Delete» of each kind of row; the Hub admin's is the row's delete() (tax categories have only that).
DELETE_OPERATIONS = {
    Product: ("inventory.product.delete", ProductRefIn),
    Category: ("inventory.category.delete", CategoryRefIn),
}


def run(name, data):
    return get(name)(ctx_for("hub_admin"), data)


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # reported to the test, which fails on it
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def remove(target, how: str) -> None:
    if how == "operation":
        name, ref = DELETE_OPERATIONS[type(target)]
        run(name, ref(id=target.id))
    else:
        # What the Hub admin's «Delete» does: ModelAdmin.delete_model is the row's delete().
        type(target).objects.get(pk=target.pk).delete()


def delete(target, how: str) -> None:
    """Deletes ``target`` in this session, giving up after LOCK_TIMEOUT on a row another session holds. The
    lock timeout is the transaction's (SET LOCAL): a session-level one would go back with the connection and
    reach the tests after this one (the autouse fixture of conftest.py fails a test that leaves it)."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        remove(target, how)


@contextmanager
def deleted_after_the_first_read_of(target, how: str):
    """Commits the deletion of ``target`` in another session right after the first statement of this one
    that reads its table: a deletion landing in the middle of a read, every time."""
    table = f'FROM "{type(target)._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete(target, how)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


@contextmanager
def deleted_just_before(statement: str, target, how: str):
    """Deletes ``target`` in another session right before the first statement of this one that starts with
    ``statement`` (the write that names it): between the read that found it and the write, every time. It
    commits, or waits for this session when it holds the row (and gives up)."""
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        if not deletions and sql.lstrip().startswith(statement):
            deletions.extend(at_once(lambda: delete(target, how)))
        return execute(sql, params, many, context)

    with connection.execute_wrapper(wrapper):
        yield deletions


@contextmanager
def deleted_in_flight(target, how: str):
    """A deletion of ``target`` under way in another session when this one first reads its table: it holds
    the row, as a deletion takes it first, and commits a moment later while this one goes on."""
    table = f'FROM "{type(target)._meta.db_table}"'
    holds = threading.Event()
    deletions: list = []

    def deletion():
        try:
            with transaction.atomic():
                type(target).objects.select_for_update().get(pk=target.pk)
                holds.set()
                time.sleep(IN_FLIGHT)
                remove(target, how)
            deletions.append("ok")
        except Exception as error:  # reported to the test, which fails on it
            deletions.append(repr(error))
        finally:
            holds.set()
            connection.close()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, context):
        if thread.ident is None and sql.lstrip().upper().startswith("SELECT") and table in sql:
            thread.start()
            holds.wait(5)
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(wrapper):
            yield deletions
    finally:
        if thread.ident is not None:
            thread.join(30)


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


def sqlstate(error) -> str | None:
    while error is not None:
        if getattr(error, "sqlstate", None):
            return error.sqlstate
        error = error.__cause__ or error.__context__
    return None


def held(deletions) -> bool:
    """The deletion waited for the row this write holds (and gave up)."""
    return len(deletions) == 1 and sqlstate(deletions[0]) == LOCK_NOT_AVAILABLE


def attempt(call):
    """What ``call`` answers: its result, or the error it is refused with (a 500 is raised as it comes)."""
    try:
        return call()
    except OperationError as error:
        return error


# The detail of a product


def a_categorized_product() -> Product:
    product = Product.objects.create(name="Espresso", sku="ESP-1", price=150)
    ProductCategory.objects.create(product=product, category=Category.objects.create(name="Coffee", slug="coffee"))
    return product


@pytest.mark.parametrize("how", DELETIONS)
def test_a_product_deleted_while_its_detail_is_read_is_never_a_server_error(how):
    espresso = a_categorized_product()
    with deleted_after_the_first_read_of(espresso, how) as deletions:
        detail = run("inventory.product.get", ProductRefIn(id=espresso.id))
    assert deleted(deletions) == ["ok"]
    # The product as it was read: its own row (its links may already be gone with it).
    assert (detail.id, detail.name, detail.sku, detail.price, detail.is_active) == (
        espresso.id,
        "Espresso",
        "ESP-1",
        150,
        True,
    )
    # What runs next (the deletion's event re-runs the open detail, a reload): not found, with the app's key.
    with pytest.raises(NotFound) as error:
        run("inventory.product.get", ProductRefIn(id=espresso.id))
    assert (error.value.code, error.value.status) == ("not_found", 404)


def test_the_detail_reads_the_product_once():
    # The read that finds the product is the one that loads its row: no second read for a deletion to fall into.
    espresso = a_categorized_product()
    with CaptureQueriesContext(connection) as read:
        detail = run("inventory.product.get", ProductRefIn(id=espresso.id))
    reads = [query["sql"] for query in read.captured_queries if f'FROM "{Product._meta.db_table}"' in query["sql"]]
    assert len(reads) == 1, reads
    assert (detail.id, len(detail.category_ids), detail.tracks_stock) == (espresso.id, 1, True)


@pytest.mark.parametrize("how", DELETIONS)
def test_a_product_deleted_between_its_name_and_its_detail_is_not_found(how):
    espresso = a_categorized_product()
    with deleted_after_the_first_read_of(espresso, how) as deletions:
        with pytest.raises(NotFound) as error:
            run("inventory.product.get", ProductRefIn(product="esp-1"))
    assert (deleted(deletions), error.value.code, error.value.status) == (["ok"], "not_found", 404)


# The writes that name a category or a tax category


@pytest.fixture
def world():
    general = TaxCategory.objects.create(key=GENERAL, name="General")
    return SimpleNamespace(
        general=general,
        # Named by nothing yet, so the staff may delete it in the Hub admin.
        probe=TaxCategory.objects.create(key=PROBE, name="Probe"),
        espresso=Product.objects.create(name="Espresso", sku="ESP-1", price=150, tax_category=general),
        coffee=Category.objects.create(name="Coffee", slug="coffee"),
    )


#: Each write that puts a product in ``coffee``, and what it answers when the category is gone (the same as
#: for one deleted before: a link is 404, a product's form says which field).
CATEGORY_WRITES = {
    "link": (
        lambda w: run(
            "inventory.product_category.add",
            ProductCategoryIn(product_id=w.espresso.id, category_id=w.coffee.id),
        ),
        (404, "not_found", None),
    ),
    "create": (
        lambda w: run(
            "inventory.product.create",
            ProductIn(name="Latte", sku="LAT-1", price=200, tax_category_key=GENERAL, category_ids=[w.coffee.id]),
        ),
        (422, "invalid_field", ["category_ids"]),
    ),
    "update": (
        lambda w: run("inventory.product.update", ProductPatchIn(id=w.espresso.id, category_ids=[w.coffee.id])),
        (422, "invalid_field", ["category_ids"]),
    ),
}


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(CATEGORY_WRITES))
def test_a_category_deleted_while_a_product_is_put_in_it_waits_for_the_write(world, write, how):
    call, _ = CATEGORY_WRITES[write]
    with deleted_just_before('INSERT INTO "inventory_productcategory"', world.coffee, how) as deletions:
        call(world)
    # Never a product hanging from a deleted category.
    assert not ProductCategory.objects.filter(category__is_deleted=True).exists()
    assert held(deletions), deleted(deletions)
    assert ProductCategory.objects.filter(category=world.coffee, category__is_deleted=False).count() == 1


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(CATEGORY_WRITES))
def test_a_category_being_deleted_when_a_product_is_put_in_it_is_not_found(world, write, how):
    call, (status, code, fields) = CATEGORY_WRITES[write]
    with deleted_in_flight(world.coffee, how) as deletions:
        outcome = attempt(lambda: call(world))
    assert deletions == ["ok"]
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code, list(outcome.fields) if fields else None) == (status, code, fields)
    assert not ProductCategory.objects.filter(category_id=world.coffee.id).exists()
    assert not Product.objects.filter(sku="LAT-1").exists()


def _import_products(w):
    row = {"line": 2, "name": "Latte", "sku": "LAT-1", "price": "2", "tax_category_key": PROBE}
    return run("inventory.product.bulk_create", ProductImportIn(rows=[row]))


def _import_categories(w):
    return run("inventory.category.bulk_create", CategoryImportIn(rows=[{"line": 2, "name": "Tea", "tax_category_key": PROBE}]))


#: Each write that names the tax category ``probe``, and the statement that writes it down.
TAX_WRITES = {
    "product.create": (
        lambda w: run("inventory.product.create", ProductIn(name="Latte", sku="LAT-1", price=200, tax_category_key=PROBE)),
        'INSERT INTO "inventory_product" (',
    ),
    "product.update": (
        lambda w: run("inventory.product.update", ProductPatchIn(id=w.espresso.id, tax_category_key=PROBE)),
        'UPDATE "inventory_product" SET',
    ),
    "product.import": (_import_products, 'INSERT INTO "inventory_product" ('),
    "category.create": (
        lambda w: run("inventory.category.create", CategoryIn(name="Tea", tax_category_key=PROBE)),
        'INSERT INTO "inventory_category" (',
    ),
    "category.update": (
        lambda w: run("inventory.category.update", CategoryPatchIn(id=w.coffee.id, tax_category_key=PROBE)),
        'UPDATE "inventory_category" SET',
    ),
    "category.import": (_import_categories, 'INSERT INTO "inventory_category" ('),
}


def named_by(tax: TaxCategory) -> int:
    return Product.objects.filter(tax_category=tax).count() + Category.objects.filter(tax_category=tax).count()


@pytest.mark.parametrize("write", sorted(TAX_WRITES))
def test_a_tax_category_deleted_while_a_write_names_it_waits_for_the_write(world, write):
    call, statement = TAX_WRITES[write]
    with deleted_just_before(statement, world.probe, "row") as deletions:
        call(world)
    assert held(deletions), deleted(deletions)
    assert named_by(world.probe) == 1


@pytest.mark.parametrize("write", sorted(TAX_WRITES))
def test_a_tax_category_being_deleted_when_a_write_names_it_is_refused(world, write):
    call, _ = TAX_WRITES[write]
    with deleted_in_flight(world.probe, "row") as deletions:
        outcome = attempt(lambda: call(world))
    assert deletions == ["ok"]
    assert not TaxCategory.objects.filter(pk=world.probe.pk).exists()
    # As for a key that does not exist: the form says which field; an import, which row.
    if write.endswith(".import"):
        assert [(row.status, row.line) for row in outcome.rows] == [("failed", 2)], outcome
    else:
        assert isinstance(outcome, OperationError), outcome
        assert (outcome.status, outcome.code, list(outcome.fields)) == (422, "invalid_field", ["tax_category_key"])
    assert not Product.objects.filter(sku="LAT-1").exists() and not Category.objects.filter(name="Tea").exists()
    assert Product.objects.get(pk=world.espresso.pk).tax_category_id == world.general.id
    assert Category.objects.get(pk=world.coffee.pk).tax_category_id is None
