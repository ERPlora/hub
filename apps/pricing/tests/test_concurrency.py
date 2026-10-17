"""Two people at once: real sessions in threads, real row locks and unique indexes (WORKBOOK «Para quien
lo mantiene»). Two «make it general» at the same moment leave one general list; two lists, two rules
or two prices with the same code or quantity at once leave one, and the other is told why.

A write that names another app's row (the category or product of a rule, the product of a price, the
customer group of a list or a rule) read it unheld: a deletion committed between that read and the write
either left the rule, price or list pointing at a row that is gone or, the Hub admin's, made the database
refuse the write (a 500). A write holds what it names, so the deletion waits for it; one already under way
when the write reads it is not found, as one deleted before. Both the business's «Delete» and the Hub
admin's (the row's delete()) are landed there.
"""

import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import connection, transaction
from live.errors import OperationError
from live.operations import get

from apps.customer.models import CustomerGroup
from apps.inventory.models import Category, Product
from apps.pricing.models import DiscountRule, PriceItem, PriceList

from .conftest import ctx_for, make_category, make_group, make_list, make_product, make_rule

pytestmark = pytest.mark.django_db(transaction=True)


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # an expected refusal or an unexpected failure, both reported
            results[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def test_two_lists_made_general_at_once_leave_one_general_list():
    make_list("OLD", is_default=True)
    make_list("A")
    make_list("B")
    results = at_once(*(lambda code=code: run("pricing.price_list.set_default", {"price_list": code}) for code in ("A", "B")))
    assert not [result for result in results if isinstance(result, Exception)], results
    assert PriceList.objects.filter(is_default=True).count() == 1
    assert PriceList.objects.get(is_default=True).code in {"A", "B"}


def test_two_general_lists_created_at_once_leave_one():
    results = at_once(
        *(lambda code=code: run("pricing.price_list.create", {"code": code, "name": code, "is_default": True}) for code in "XYZ")
    )
    assert not [result for result in results if isinstance(result, Exception)], results
    assert PriceList.objects.count() == 3
    assert PriceList.objects.filter(is_default=True).count() == 1


def test_the_same_code_at_once_makes_one_list_and_one_rule():
    lists = at_once(*(lambda case=case: run("pricing.price_list.create", {"code": case, "name": "VIP"}) for case in ("VIP", "vip")))
    refused = [result for result in lists if isinstance(result, OperationError)]
    assert len(refused) == 1 and refused[0].code == "pricing.duplicate_code"
    assert PriceList.objects.count() == 1
    rule = {"name": "Ten", "rule_type": "percent", "percent": "10"}
    rules = at_once(*(lambda: run("pricing.rule.create", {"code": "TEN", **rule}) for _ in range(2)))
    refused = [result for result in rules if isinstance(result, OperationError)]
    assert len(refused) == 1 and refused[0].code == "pricing.duplicate_code"
    assert DiscountRule.objects.count() == 1


def test_the_same_price_at_once_is_put_once():
    make_list("VIP")
    product = make_product("Shampoo", "SH-1")
    data = {"price_list": "VIP", "product_id": str(product.id), "price": 1000, "min_quantity": "5"}
    results = at_once(*(lambda: run("pricing.price_item.add", data) for _ in range(2)))
    refused = [result for result in results if isinstance(result, OperationError)]
    assert len(refused) == 1 and refused[0].code == "pricing.price_item_exists"
    assert PriceItem.objects.count() == 1


# A row another write names, deleted at the same time


DELETIONS = ["operation", "row"]
#: A deletion gives up after this on a row another session holds (a real one waits for its COMMIT).
LOCK_TIMEOUT = "300ms"
#: Postgres' ``lock_not_available``: the deletion found the row held.
LOCK_NOT_AVAILABLE = "55P03"
#: How long a deletion under way holds its row before it commits.
IN_FLIGHT = 0.5
#: The business's «Delete» of each kind of row; the Hub admin's is the row's delete().
DELETE_OPERATIONS = {
    Category: "inventory.category.delete",
    Product: "inventory.product.delete",
    CustomerGroup: "customer.group.delete",
}


def remove(target, how: str) -> None:
    if how == "operation":
        run(DELETE_OPERATIONS[type(target)], {"id": str(target.id)})
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


@pytest.fixture
def world():
    group = make_group("VIP")
    return SimpleNamespace(
        coffee=make_category("Coffee", slug="coffee"),
        espresso=make_product("Espresso", "ESP-1"),
        vip=group,
        general=make_list("GEN", name="General"),
        # Applies to everything, with no group: a write gives it a target or a group.
        open_rule=make_rule("ALL"),
        # Off, for the VIP group: turning it on asks whether the group still exists.
        vip_rule=make_rule("VIPOFF", is_active=False, customer_group_id=group.id),
    )


TEN = {"name": "Ten", "rule_type": "percent", "percent": "10"}

#: Each write that names a category or a product: the statement that writes it down, what it names, how it
#: is refused when that is gone (the same as for one deleted before: a rule's form says which field, a price
#: is not found), and what the write leaves pointing at it when it goes through.
TARGET_WRITES = {
    "rule.create.category": (
        lambda w: run("pricing.rule.create", {"code": "TEN", **TEN, "applies_to": "category", "category_id": str(w.coffee.id)}),
        'INSERT INTO "pricing_discountrule"',
        "coffee",
        (422, "invalid_field", ["category_id"]),
    ),
    "rule.create.product": (
        lambda w: run("pricing.rule.create", {"code": "TEN", **TEN, "applies_to": "product", "product": "esp-1"}),
        'INSERT INTO "pricing_discountrule"',
        "espresso",
        (422, "invalid_field", ["product"]),
    ),
    "rule.update.category": (
        lambda w: run("pricing.rule.update", {"id": str(w.open_rule.id), "applies_to": "category", "category": "Coffee"}),
        'UPDATE "pricing_discountrule" SET',
        "coffee",
        (422, "invalid_field", ["category"]),
    ),
    "rule.update.product": (
        lambda w: run("pricing.rule.update", {"id": str(w.open_rule.id), "applies_to": "product", "product_id": str(w.espresso.id)}),
        'UPDATE "pricing_discountrule" SET',
        "espresso",
        (422, "invalid_field", ["product_id"]),
    ),
    "price_item.add": (
        lambda w: run("pricing.price_item.add", {"price_list": "GEN", "product_id": str(w.espresso.id), "price": 120}),
        'INSERT INTO "pricing_priceitem"',
        "espresso",
        (404, "not_found", None),
    ),
}


def pointing_at(target) -> int:
    """The rules and prices that point at ``target`` (a category or a product)."""
    if isinstance(target, Category):
        return DiscountRule.objects.filter(category=target).count()
    return DiscountRule.objects.filter(product=target).count() + PriceItem.objects.filter(product=target).count()


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(TARGET_WRITES))
def test_a_category_or_product_deleted_while_a_write_names_it_waits_for_the_write(world, write, how):
    call, statement, name, _ = TARGET_WRITES[write]
    target = getattr(world, name)
    with deleted_just_before(statement, target, how) as deletions:
        call(world)
    # Never a rule or a price pointing at a deleted category or product.
    assert not DiscountRule.objects.filter(category__is_deleted=True).exists()
    assert not DiscountRule.objects.filter(product__is_deleted=True).exists()
    assert not PriceItem.objects.filter(product__is_deleted=True).exists()
    assert held(deletions), deleted(deletions)
    assert not type(target).objects.get(pk=target.pk).is_deleted
    assert pointing_at(target) == 1


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(TARGET_WRITES))
def test_a_category_or_product_being_deleted_when_a_write_names_it_is_refused(world, write, how):
    call, _, name, (status, code, fields) = TARGET_WRITES[write]
    target = getattr(world, name)
    with deleted_in_flight(target, how) as deletions:
        outcome = attempt(lambda: call(world))
    assert deletions == ["ok"]
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code, list(outcome.fields) if fields else None) == (status, code, fields)
    assert not DiscountRule.objects.filter(code="TEN").exists() and not PriceItem.objects.exists()
    assert DiscountRule.objects.values_list("applies_to", "category_id", "product_id").get(pk=world.open_rule.pk) == (
        "all",
        None,
        None,
    )


#: Each write that names the customer group VIP: the statement that writes it down, how it is refused when
#: the group is gone (the same as for one deleted before) and what it leaves pointing at the group.
GROUP_WRITES = {
    "price_list.create": (
        lambda w: run("pricing.price_list.create", {"code": "VIP", "name": "VIP", "customer_group": "VIP"}),
        'INSERT INTO "pricing_pricelist"',
        (422, "invalid_field", ["customer_group"]),
    ),
    "price_list.update": (
        lambda w: run("pricing.price_list.update", {"id": str(w.general.id), "customer_group_id": str(w.vip.id)}),
        'UPDATE "pricing_pricelist" SET',
        (422, "invalid_field", ["customer_group_id"]),
    ),
    "rule.create": (
        lambda w: run("pricing.rule.create", {"code": "TEN", **TEN, "customer_group_id": str(w.vip.id)}),
        'INSERT INTO "pricing_discountrule"',
        (422, "invalid_field", ["customer_group_id"]),
    ),
    "rule.update": (
        lambda w: run("pricing.rule.update", {"id": str(w.open_rule.id), "customer_group": "VIP"}),
        'UPDATE "pricing_discountrule" SET',
        (422, "invalid_field", ["customer_group"]),
    ),
    "rule.activate": (
        lambda w: run("pricing.rule.activate", {"id": str(w.vip_rule.id)}),
        'UPDATE "pricing_discountrule" SET',
        (409, "pricing.rule_group_deleted", None),
    ),
}


def for_the_group(group) -> tuple[int, int]:
    """The lists and the active rules of ``group``."""
    lists = PriceList.objects.filter(customer_group_id=group.id).count()
    return lists, DiscountRule.objects.filter(customer_group_id=group.id, is_active=True).count()


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(GROUP_WRITES))
def test_a_customer_group_deleted_while_a_write_names_it_waits_for_the_write(world, write, how):
    call, statement, _ = GROUP_WRITES[write]
    with deleted_just_before(statement, world.vip, how) as deletions:
        call(world)
    assert held(deletions), deleted(deletions)
    # The group is still there for the list or the rule that now names it.
    assert CustomerGroup.objects.filter(pk=world.vip.pk).exists()
    assert sum(for_the_group(world.vip)) == 1


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(GROUP_WRITES))
def test_a_customer_group_being_deleted_when_a_write_names_it_is_refused(world, write, how):
    call, _, (status, code, fields) = GROUP_WRITES[write]
    with deleted_in_flight(world.vip, how) as deletions:
        outcome = attempt(lambda: call(world))
    assert deletions == ["ok"]
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code, list(outcome.fields) if fields else None) == (status, code, fields)
    # Nothing names the group that is gone: no list for it, no rule on for it.
    assert for_the_group(world.vip) == (0, 0)
