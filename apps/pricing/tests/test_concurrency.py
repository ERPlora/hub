"""Two people at once: real sessions in threads, real row locks and unique indexes (WORKBOOK «Para quien
lo mantiene»). Two «make it general» at the same moment leave one general list; two lists, two rules
or two prices with the same code or quantity at once leave one, and the other is told why.

A write that names another app's row (the category or product of a rule, the product of a price, the
customer group of a list or a rule) read it unheld: a deletion committed between that read and the write
either left the rule, price or list pointing at a row that is gone or, the Hub admin's, made the database
refuse the write (a 500). A write holds what it names, so the deletion waits for it; one already under way
when the write reads it is not found, as one deleted before. Both the business's «Delete» and the Hub
admin's (the row's delete()) are landed there.

The detail of a price list that a deletion lands in the middle of answers what it read or 404, never a 500.

A write on a price list holds it from the read that finds it, so a change to the same list by somebody else
waits for it: unheld, the write saved the whole row it had read and undid that change, or the database refused
it (a 500). Making a list the general one holds the list that has the mark until it takes it: unheld, the Hub
admin's deletion of that list went in between and taking the mark found no row (a 500).
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import connections
from live.errors import OperationError
from live.operations import atomic, get

from apps.customer.models import CustomerGroup
from apps.customer.schemas.fields import GroupRefIn
from apps.inventory.models import Category
from apps.inventory.tests import test_concurrency as inventory
from apps.inventory.tests.test_concurrency import (
    DELETIONS,
    LOCK_TIMEOUT,
    attempt,
    deleted,
    deleted_after_the_first_read_of,
    deleted_in_flight,
    deleted_just_before,
    held,
)
from apps.pricing.models import DiscountRule, PriceItem, PriceList
from base.tenancy.context import current_alias
from base.tenancy.tests.concurrency import at_once

from .conftest import HUB_DB_COMMITTED, ctx_for, make_category, make_group, make_item, make_list, make_product, make_rule

#: Several sessions of the business at once, each committing: its plan has room for them all.
pytestmark = [HUB_DB_COMMITTED, pytest.mark.usefixtures("plan_with_room")]


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


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


@pytest.fixture(autouse=True)
def the_business_deletes_a_customer_group_too(monkeypatch):
    """Inventory's deletion helpers delete a product or a category as the business does; a customer group the same
    way, with Customers' «Delete»."""
    monkeypatch.setitem(inventory.DELETE_OPERATIONS, CustomerGroup, ("customer.group.delete", GroupRefIn))


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


# The detail of a price list: a deletion that lands in the middle of a read


@pytest.fixture
def vip_list(world):
    """A list of the VIP group with one price: what its detail shows beyond its own columns."""
    price_list = make_list("VIPL", name="VIP list", customer_group_id=world.vip.id)
    make_item(price_list, world.espresso, price=120)
    return price_list


# Only the Hub admin deletes a price list (the row goes, its prices with it): the business deactivates it.
def test_a_price_list_deleted_while_its_detail_is_read_is_never_a_server_error(vip_list):
    # The detail found the list and then read it again for its group's name and its count of prices: a
    # deletion committed between the two raised DoesNotExist (a 500). In one read it is the list as it was read.
    with deleted_after_the_first_read_of(vip_list, "row") as deletions:
        shown = run("pricing.price_list.get", {"id": str(vip_list.pk)})
    assert deleted(deletions) == ["ok"]
    assert (shown.id, shown.code, shown.customer_group_name, shown.item_count) == (vip_list.pk, "VIPL", "VIP", 1)
    # What the detail answers next: not found, and the open sheet closes.
    gone = attempt(lambda: run("pricing.price_list.get", {"id": str(vip_list.pk)}))
    assert isinstance(gone, OperationError), gone
    assert (gone.status, gone.code) == (404, "pricing.price_list_not_found")


def test_a_price_list_deleted_between_its_name_and_its_detail_is_not_found(vip_list):
    with deleted_after_the_first_read_of(vip_list, "row") as deletions:
        outcome = attempt(lambda: run("pricing.price_list.get", {"price_list": "vipl"}))
    assert deleted(deletions) == ["ok"]
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (404, "pricing.price_list_not_found")


def test_find_list_refuses_to_lock_the_rows_it_is_given(vip_list):
    # ``rows`` is what a detail shows (the group's name, the count of prices: grouped), and Postgres refuses
    # ``FOR UPDATE`` on a grouped query. A write names its list without ``rows``; both at once is a mistake
    # of the caller, told as such and not as a database error.
    from apps.pricing.queries.reads import find_list
    from apps.pricing.queries.rows import _lists

    with atomic(), pytest.raises(TypeError, match="rows"):
        find_list(vip_list.pk, None, lock=True, rows=_lists())


# A product back from the separate copy (PRICING-F14): its rules come back on as the platform switched them off


@contextmanager
def changed_by_hand_just_before(statement: str, name: str, data: dict):
    """The business runs the operation ``name`` with ``data`` in another session right before the first statement
    of this one that starts with ``statement``: between the read that found the row and the write. It commits, or
    gives up after LOCK_TIMEOUT on the row this session holds."""
    changes: list = []

    def change():
        with atomic():
            with connections[current_alias()].cursor() as cursor:
                cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
            run(name, data)

    def wrapper(execute, sql, params, many, context):
        if not changes and sql.lstrip().startswith(statement):
            changes.extend(at_once(change))
        return execute(sql, params, many, context)

    with connections[current_alias()].execute_wrapper(wrapper):
        yield changes


def test_a_rule_switched_back_on_with_its_product_is_held_against_a_change_by_hand(world):
    from live.context import system_context

    from .conftest import A

    rule = make_rule("ESP", applies_to="product", product=world.espresso)
    reaction = get("pricing.catalog.forget_product")
    reaction(system_context(A), reaction.input.model_validate({"id": str(world.espresso.id)}))
    recall = get("pricing.catalog.recall_product")

    rename = {"id": str(rule.id), "name": "Renamed by hand"}
    with changed_by_hand_just_before('UPDATE "pricing_discountrule" SET', "pricing.rule.update", rename) as changes:
        recall(system_context(A), recall.input.model_validate({"id": str(world.espresso.id)}))

    # Unheld, the business's change went in between and the rule it touched came back on all the same.
    assert held(changes), changes
    rule.refresh_from_db()
    assert (rule.is_active, rule.name) == (True, "Rule ESP")


# The general mark and the list a write is on, held from the read that finds them


@pytest.fixture
def lists():
    return SimpleNamespace(general=make_list("OLD", is_default=True), spring=make_list("SPRING", name="Spring"))


#: Each way to make a list the general one, and the code of the list that takes the mark.
TAKE_THE_MARK = {
    "price_list.set_default": (lambda: run("pricing.price_list.set_default", {"price_list": "SPRING"}), "SPRING"),
    "price_list.create": (lambda: run("pricing.price_list.create", {"code": "NEW", "name": "New", "is_default": True}), "NEW"),
}


def general_codes() -> list[str]:
    return list(PriceList.objects.filter(is_default=True).values_list("code", flat=True))


@pytest.mark.parametrize("way", sorted(TAKE_THE_MARK))
def test_the_general_list_deleted_while_another_takes_its_mark_waits_for_it(lists, way):
    call, code = TAKE_THE_MARK[way]
    with deleted_just_before('UPDATE "pricing_pricelist" SET', lists.general, "row") as deletions:
        call()
    assert held(deletions), deleted(deletions)
    assert general_codes() == [code]
    assert PriceList.objects.filter(pk=lists.general.pk, is_default=False).exists()


@pytest.mark.parametrize("way", sorted(TAKE_THE_MARK))
def test_the_general_list_being_deleted_when_another_takes_its_mark_leaves_the_new_one_general(lists, way):
    call, code = TAKE_THE_MARK[way]
    with deleted_in_flight(lists.general, "row") as deletions:
        call()
    assert deletions == ["ok"]
    assert general_codes() == [code]
    assert not PriceList.objects.filter(pk=lists.general.pk).exists()


#: Each write that holds the list SPRING from the read that finds it: the call, the statement it writes with,
#: what the business does to the same list by hand meanwhile, and what the write leaves the list as. Unheld, the
#: change by hand went in between: the write's whole-row save undid it (a name, a last day), the database
#: refused the write (a general list switched off: a 500), or a price went into a list that was switched off.
LIST_WRITES = {
    "price_list.update": (
        lambda: run("pricing.price_list.update", {"price_list": "SPRING", "name": "Spring 2027"}),
        'UPDATE "pricing_pricelist" SET',
        ("pricing.price_list.update", {"price_list": "SPRING", "valid_until": "2027-06-30"}),
        {"name": "Spring 2027", "valid_until": None},
    ),
    "price_list.set_default": (
        lambda: run("pricing.price_list.set_default", {"price_list": "SPRING"}),
        'UPDATE "pricing_pricelist" SET',
        ("pricing.price_list.update", {"price_list": "SPRING", "name": "Renamed by hand"}),
        {"name": "Spring", "is_default": True},
    ),
    "price_list.deactivate": (
        lambda: run("pricing.price_list.deactivate", {"price_list": "SPRING"}),
        'UPDATE "pricing_pricelist" SET',
        ("pricing.price_list.set_default", {"price_list": "SPRING"}),
        {"is_active": False, "is_default": False},
    ),
    "price_item.add": (
        lambda: run("pricing.price_item.add", {"price_list": "SPRING", "product": "ESP-1", "price": 120}),
        'INSERT INTO "pricing_priceitem"',
        ("pricing.price_list.deactivate", {"price_list": "SPRING"}),
        {"is_active": True, "items__price": 120},
    ),
}


@pytest.mark.parametrize("write", sorted(LIST_WRITES))
def test_a_price_list_changed_by_hand_while_a_write_holds_it_waits_for_the_write(lists, write):
    make_product("Espresso", "ESP-1")
    call, statement, (name, data), left = LIST_WRITES[write]
    with changed_by_hand_just_before(statement, name, data) as changes:
        call()
    assert held(changes), changes
    assert PriceList.objects.filter(pk=lists.spring.pk, **left).exists()
