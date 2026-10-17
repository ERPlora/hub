"""A product deleted while its detail is read: real sessions in threads.

The detail found the product and then loaded it again by its id, so a deletion committed between the two
reads handed ``None`` to the output (a 500). A read that a deletion lands in the middle of answers what it
read or 404, never a 500; both the business's «Delete» (the row stays, marked deleted) and the Hub admin's
(the row goes) are landed there.
"""

import threading
from contextlib import contextmanager

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from live.errors import NotFound
from live.operations import get

from apps.inventory.models import Category, Product, ProductCategory
from apps.inventory.schemas import ProductRefIn

from .conftest import ctx_for

pytestmark = pytest.mark.django_db(transaction=True)

DELETIONS = ["operation", "row"]
#: The deletion gives up after this on a row another session holds (none here: a read holds nothing).
LOCK_TIMEOUT = "300ms"


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


def delete(product, how: str) -> None:
    """Deletes ``product`` in this session. The lock timeout is the transaction's (SET LOCAL): a
    session-level one would go back with the connection and reach the tests after this one."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        if how == "operation":
            run("inventory.product.delete", ProductRefIn(id=product.id))
        else:
            # What the Hub admin's «Delete» does: ModelAdmin.delete_model is the row's delete().
            Product.objects.get(pk=product.pk).delete()


@contextmanager
def deleted_after_the_first_read_of(product, how: str):
    """Commits the deletion of ``product`` in another session right after the first statement of this
    one that reads the products: a deletion landing in the middle of the detail, every time."""
    table = f'FROM "{Product._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete(product, how)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


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
