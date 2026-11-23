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

import uuid
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import connections
from live.errors import NotFound, OperationError
from live.models import OutboxEvent

from apps.inventory.models import Category, Product
from apps.inventory.tests.test_concurrency import attempt, deleted, deleted_in_flight, deleted_just_before, held
from apps.modifier.models import ModifierGroup, ModifierLink, ModifierOption
from apps.tax.models import TaxCategory
from base.recovery import actor_of
from base.tenancy.context import current_alias
from base.tenancy.tests.concurrency import at_once, meanwhile

from .conftest import HUB_DB_COMMITTED, ctx_with, make_product, run

#: Several sessions of the business at once, each committing: its plan has room for them all.
pytestmark = [HUB_DB_COMMITTED, pytest.mark.usefixtures("plan_with_room")]


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
        lambda: run("modifier.option.create", {"group": "Sauces", "name": "Mayo", "price_delta": 0}),
        lambda: run("modifier.option.create", {"group": "Sauces", "name": "mayo", "price_delta": 0}),
    )
    assert codes(results) == ["modifier.option_name_taken", "ok"]
    assert ModifierOption.objects.count() == 1


def test_the_same_link_twice_at_once_one_wins():
    run("modifier.group.create", {"name": "Sauces"})
    # A committed test finds business A emptied by the one before, Taxes' factory catalogue too: one category of its own.
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
    rare = run("modifier.option.create", {"group": "Doneness", "name": "Rare", "price_delta": 0})
    medium = run("modifier.option.create", {"group": "Doneness", "name": "Medium", "price_delta": 0})
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
        {"group": "Sauces", "name": "Ketchup", "is_default": True, "price_delta": 0},
    )
    results = at_once(
        lambda: run(
            "modifier.option.create",
            {"group": "Sauces", "name": "Mayo", "is_default": True, "price_delta": 0},
        ),
        lambda: run(
            "modifier.option.create",
            {"group": "Sauces", "name": "Mustard", "is_default": True, "price_delta": 0},
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

    with connections[current_alias()].execute_wrapper(wrapper):
        yield deletions


def test_a_group_deleted_while_its_detail_is_read_is_never_a_server_error():
    # hub#34: the detail found the group and then loaded it by its id in a second read; a deletion
    # committed between the two raised DoesNotExist (a 500). In one read it is the group as it was read.
    sauces = run("modifier.group.create", {"name": "Sauces"})
    run("modifier.option.create", {"group": "Sauces", "name": "Mayo", "price_delta": 0})
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
GENERAL, PROBE = "test.general", "test.probe"


@pytest.fixture
def world():
    # A committed test finds business A emptied by the one before, Taxes' factory catalogue too: categories of its own.
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


def reading(table: str):
    """Whether a statement is this session's read of ``table``."""
    return lambda sql: sql.lstrip().upper().startswith("SELECT") and f'FROM "{table}"' in sql


def test_a_default_the_business_chooses_while_an_option_comes_back_is_never_taken_from_it():
    sauces = run("modifier.group.create", {"name": "Sauces", "max_choices": 1})
    ketchup = run("modifier.option.create", {"group": "Sauces", "name": "Ketchup", "price_delta": 0})
    recovery = actor_of(uuid.uuid7())
    choose = lambda: run("modifier.option.update", {"id": str(ketchup.id), "is_default": True})  # noqa: E731

    # The recovery has just read that the group has room for its option chosen by default.
    with meanwhile(reading(ModifierOption._meta.db_table), choose) as chosen:
        run(
            "modifier.option.recover",
            {"group_id": str(sauces.id), "name": "Alioli", "price_delta": 0, "is_default": True},
            ctx=ctx_with("*", actor=recovery),
        )

    # The business's choice waited for the group the recovery held, and stands: the recovery changed nothing of its own.
    assert codes(chosen) == ["ok"]
    assert list(ModifierOption.objects.filter(is_default=True).values_list("name", flat=True)) == ["Ketchup"]
    assert list(OutboxEvent.objects.filter(actor=recovery).values_list("name", flat=True)) == ["modifier.option.created"]
