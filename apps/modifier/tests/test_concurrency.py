"""Two people saving at once: real sessions in threads, real constraints and row locks.

Whoever comes first wins; the other one is refused with the real reason (the same 409 as the check
before writing), never with a duplicated name, a duplicated link or two defaults in a group of one.
A read that a deletion lands in the middle of answers what it read or 404, never a 500.

The writes that name a product or a category of Inventory (applying a group to it) or a tax category of
Taxes (an option created or edited with its own) read it unheld: a deletion committed between that read and
the write either left a group applied to a deleted product or category or, the Hub admin's, made the
database refuse the write at its COMMIT (a 500). A write holds what it names, so the deletion waits for it;
one already under way when the write reads it is not found, as one deleted before. Both the business's
«Delete» (the row stays, marked deleted) and the Hub admin's (the row goes) are landed there.
"""

import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import connection, transaction
from live.errors import NotFound, OperationError

from apps.inventory.models import Category, Product
from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.tax.models import TaxCategory

from .conftest import make_product, run

pytestmark = pytest.mark.django_db(transaction=True)


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except OperationError as error:
            results[index] = error
        except Exception as error:  # an unexpected failure is reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def codes(results) -> list[str]:
    return sorted(
        getattr(result, "code", "ok")
        if isinstance(result, OperationError) or not isinstance(result, Exception)
        else repr(result)
        for result in results
    )


def test_two_groups_with_the_same_name_at_once_one_wins():
    results = at_once(
        lambda: run("modifier.group.create", {"name": "Sauces"}),
        lambda: run("modifier.group.create", {"name": "SAUCES"}),
    )
    assert codes(results) == ["modifier.group_name_taken", "ok"]
    assert ModifierGroup.objects.count() == 1


def test_two_options_with_the_same_name_in_a_group_at_once_one_wins():
    run("modifier.group.create", {"name": "Sauces"})
    results = at_once(
        lambda: run("modifier.option.create", {"group": "Sauces", "name": "Mayo"}),
        lambda: run("modifier.option.create", {"group": "Sauces", "name": "mayo"}),
    )
    assert codes(results) == ["modifier.option_name_taken", "ok"]
    assert ModifierOption.objects.count() == 1


def test_the_same_link_twice_at_once_one_wins():
    run("modifier.group.create", {"name": "Sauces"})
    # transaction=True flushes Taxes' factory catalogue (a data migration): one category of its own.
    TaxCategory.objects.create(key="test.general", name="General")
    burger = make_product(tax="test.general")
    attach = lambda: run(
        "modifier.link.attach", {"group": "Sauces", "product_id": str(burger.id)}
    )  # noqa: E731
    assert codes(at_once(attach, attach)) == ["modifier.link_exists", "ok"]
    assert ModifierLink.objects.count() == 1


def test_two_defaults_at_once_in_a_group_of_one_leave_only_one():
    run(
        "modifier.group.create",
        {"name": "Doneness", "min_choices": 1, "max_choices": 1},
    )
    rare = run("modifier.option.create", {"group": "Doneness", "name": "Rare"})
    medium = run("modifier.option.create", {"group": "Doneness", "name": "Medium"})
    results = at_once(
        lambda: run("modifier.option.update", {"id": str(rare.id), "is_default": True}),
        lambda: run(
            "modifier.option.update", {"id": str(medium.id), "is_default": True}
        ),
    )
    assert codes(results) == ["ok", "ok"]
    assert ModifierOption.objects.filter(is_default=True).count() == 1


def test_two_defaults_at_once_never_pass_the_maximum():
    run("modifier.group.create", {"name": "Sauces", "max_choices": 2})
    run(
        "modifier.option.create",
        {"group": "Sauces", "name": "Ketchup", "is_default": True},
    )
    results = at_once(
        lambda: run(
            "modifier.option.create",
            {"group": "Sauces", "name": "Mayo", "is_default": True},
        ),
        lambda: run(
            "modifier.option.create",
            {"group": "Sauces", "name": "Mustard", "is_default": True},
        ),
    )
    assert codes(results) == ["modifier.too_many_defaults", "ok"]
    assert ModifierOption.objects.filter(is_default=True).count() == 2


def test_deleting_a_group_while_it_is_applied_never_breaks_the_commit():
    # Applying waits for the group's row: either it is applied and then deleted with the group, or the
    # group is gone and applying says so; never a link to a deleted group failing the COMMIT (a 500).
    TaxCategory.objects.create(key="test.general", name="General")
    burger = make_product(tax="test.general")
    for _ in range(5):
        run("modifier.group.create", {"name": "Sauces"})
        results = at_once(
            lambda: run("modifier.group.delete", {"group": "Sauces"}),
            lambda: run("modifier.link.attach", {"group": "Sauces", "product_id": str(burger.id)}),
        )
        assert codes(results) in (["ok", "ok"], ["not_found", "ok"]), results
        assert ModifierGroup.objects.count() == 0
        assert ModifierLink.objects.count() == 0


@contextmanager
def deleted_after_the_first_read_of(name):
    """Commits ``modifier.group.delete`` of ``name`` in another session right after the first statement of
    this one that reads the groups: a deletion landing in the middle of a read, every time."""
    table = f'"{ModifierGroup._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: run("modifier.group.delete", {"group": name})))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


def test_a_group_deleted_while_its_detail_is_read_is_never_a_server_error():
    # hub#34: the detail found the group and then loaded it by its id in a second read; a deletion
    # committed between the two raised DoesNotExist (a 500). In one read it is the group as it was read.
    sauces = run("modifier.group.create", {"name": "Sauces"})
    run("modifier.option.create", {"group": "Sauces", "name": "Mayo"})
    with deleted_after_the_first_read_of("Sauces") as deletions:
        detail = run("modifier.group.get", {"id": str(sauces.id)})
    assert codes(deletions) == ["ok"]
    assert (detail.id, detail.name, detail.option_count) == (sauces.id, "Sauces", 1)
    # What the deletion's event runs next: not found, and the open sheet closes.
    with pytest.raises(NotFound):
        run("modifier.group.get", {"id": str(sauces.id)})


def test_a_group_deleted_between_its_name_and_its_detail_is_not_found():
    run("modifier.group.create", {"name": "Sauces"})
    with deleted_after_the_first_read_of("Sauces") as deletions:
        with pytest.raises(NotFound) as error:
            run("modifier.group.get", {"group": "sauces"})
    assert (codes(deletions), error.value.code, error.value.status) == (["ok"], "not_found", 404)


# The writes that name a product, a category or a tax category

DELETIONS = ["operation", "row"]
#: A deletion gives up after this on a row another session holds (a real one waits for its COMMIT).
LOCK_TIMEOUT = "300ms"
#: Postgres' ``lock_not_available``: the deletion found the row held.
LOCK_NOT_AVAILABLE = "55P03"
#: How long a deletion under way holds its row before it commits.
IN_FLIGHT = 0.5
GENERAL, PROBE = "test.general", "test.probe"
#: The business's «Delete» of a product and of a category; the Hub admin's is the row's delete() (tax
#: categories have only that).
DELETE_OPERATIONS = {
    Product: "inventory.product.delete",
    Category: "inventory.category.delete",
}


def remove(target, how: str) -> None:
    if how == "operation":
        run(DELETE_OPERATIONS[type(target)], {"id": str(target.pk)})
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
    # transaction=True flushes Taxes' factory catalogue (a data migration): categories of its own.
    general = TaxCategory.objects.create(key=GENERAL, name="General")
    sauces = run("modifier.group.create", {"name": "Sauces"})
    return SimpleNamespace(
        general=general,
        # Named by nothing yet, so the staff may delete it in the Hub admin.
        probe=TaxCategory.objects.create(key=PROBE, name="Probe"),
        sauces=sauces,
        mayo=run("modifier.option.create", {"group": "Sauces", "name": "Mayo", "price_delta": 50}),
        burger=Product.objects.create(name="Burger", sku="BUR", price=800, tax_category=general),
        mains=Category.objects.create(name="Mains", slug="mains"),
    )


#: Each target a group is applied to: how the link names it and the row it names.
LINK_TARGETS = {
    "product": lambda w: ({"product_id": str(w.burger.id)}, w.burger),
    "category": lambda w: ({"category_id": str(w.mains.id)}, w.mains),
}


def apply_to(w, target: str):
    named, _ = LINK_TARGETS[target](w)
    return run("modifier.link.attach", {"group_id": str(w.sauces.id), **named})


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("target", sorted(LINK_TARGETS))
def test_a_product_or_category_deleted_while_a_group_is_applied_to_it_waits_for_the_write(world, target, how):
    _, row = LINK_TARGETS[target](world)
    with deleted_just_before('INSERT INTO "modifier_modifierlink"', row, how) as deletions:
        apply_to(world, target)
    # Never a group applied to a deleted product or category.
    assert not ModifierLink.objects.filter(**{f"{target}__is_deleted": True}).exists()
    assert held(deletions), deleted(deletions)
    assert ModifierLink.objects.filter(**{target: row, f"{target}__is_deleted": False}).count() == 1


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("target", sorted(LINK_TARGETS))
def test_a_product_or_category_being_deleted_when_a_group_is_applied_to_it_is_not_found(world, target, how):
    _, row = LINK_TARGETS[target](world)
    with deleted_in_flight(row, how) as deletions:
        outcome = attempt(lambda: apply_to(world, target))
    assert deletions == ["ok"]
    # As for one deleted before: not found, with the app's key.
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (404, "not_found")
    assert not ModifierLink.objects.exists()


#: Each write that names the tax category ``probe``, and the statement that writes it down.
TAX_WRITES = {
    "option.create": (
        lambda w: run(
            "modifier.option.create",
            {"group_id": str(w.sauces.id), "name": "Truffle", "price_delta": 200, "tax_category_key": PROBE},
        ),
        'INSERT INTO "modifier_modifieroption" (',
    ),
    "option.update": (
        lambda w: run("modifier.option.update", {"id": str(w.mayo.id), "tax_category_key": PROBE}),
        'UPDATE "modifier_modifieroption" SET',
    ),
}


@pytest.mark.parametrize("write", sorted(TAX_WRITES))
def test_a_tax_category_deleted_while_an_option_names_it_waits_for_the_write(world, write):
    call, statement = TAX_WRITES[write]
    with deleted_just_before(statement, world.probe, "row") as deletions:
        call(world)
    assert held(deletions), deleted(deletions)
    assert ModifierOption.objects.filter(tax_category=world.probe).count() == 1


@pytest.mark.parametrize("write", sorted(TAX_WRITES))
def test_a_tax_category_being_deleted_when_an_option_names_it_is_refused(world, write):
    call, _ = TAX_WRITES[write]
    with deleted_in_flight(world.probe, "row") as deletions:
        outcome = attempt(lambda: call(world))
    assert deletions == ["ok"]
    assert not TaxCategory.objects.filter(pk=world.probe.pk).exists()
    # As for a key that does not exist: the form says which field.
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code, list(outcome.fields)) == (422, "invalid_field", ["tax_category_key"])
    assert not ModifierOption.objects.filter(name="Truffle").exists()
    assert ModifierOption.objects.get(pk=world.mayo.id).tax_category_id is None
