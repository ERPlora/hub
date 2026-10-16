"""Two people saving at once: real sessions in threads, real constraints and row locks.

Whoever comes first wins; the other one is refused with the real reason (the same 409 as the check
before writing), never with a duplicated name, a duplicated link or two defaults in a group of one.
A read that a deletion lands in the middle of answers what it read or 404, never a 500.
"""

import threading
from contextlib import contextmanager

import pytest
from django.db import connection
from live.errors import NotFound, OperationError

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
