"""Two cooks at once (KITCHEN-F11, F12): real sessions in threads, real row locks.

Two cooks marking the same dish ready at the same instant mark it once (one History line, one event); two
recalls of the same dish, once; two writes that both find a round not saved yet save it once, with one
number; two sends of the same check, one round. A product, a category or a station deleted while a write
names it either waits for the write or refuses it as one deleted before, never a 500 nor a route to a
deleted product.
"""

import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.db import connection, transaction
from live.context import system_context
from live.errors import NotFound, OperationError
from live.models import OutboxEvent

from apps.inventory.models import Category, Product
from apps.kitchen.models import (
    CategoryRoute,
    LogEntry,
    ProductRoute,
    Station,
    Ticket,
    TicketItem,
)

from .conftest import A, add_line, ctx_for, fire, make_station, open_check, route_product, run

pytestmark = pytest.mark.django_db(transaction=True)

COOK = "hub_employee"


@pytest.fixture(autouse=True)
def factory_data(transactional_db):
    """A transactional test starts from a flushed database: tax's factory catalogue and Sales' payment
    methods are planted again, as their migrations do (idempotent)."""
    from importlib import import_module

    from django.apps import apps as registry

    with connection.schema_editor() as editor:
        for module in (
            "apps.tax.migrations.0002_factory_catalogue",
            "apps.tax.migrations.0005_retail_alcohol",
            "apps.sale.migrations.0002_factory_payment_methods",
        ):
            import_module(module).plant(registry, editor)


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
        except (
            Exception
        ) as error:  # an unexpected failure (a deadlock, an IntegrityError) is reported
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


def failures(results) -> list:
    return [result for result in results if isinstance(result, Exception)]


def as_cook(name: str, data: dict, actor: str):
    return lambda: run(name, data, ctx_for(COOK, actor=actor))


def a_round(product, *names):
    order = open_check("Table 4")
    for name in names:
        add_line(order.id, product(name))
    return fire(order.id).order


def test_two_cooks_marking_the_same_dish_ready_mark_it_once(product):
    order = a_round(product, "Burger", "Fries")
    line = order.lines[0].id
    data = {"ticket_id": str(line), "item_ids": [str(line)]}
    results = at_once(
        as_cook("kitchen.item.bump", data, "marta"),
        as_cook("kitchen.item.bump", data, "luis"),
    )
    assert failures(results) == []
    assert TicketItem.objects.get(pk=line).status == "ready"
    assert LogEntry.objects.filter(action="item_ready").count() == 1
    assert OutboxEvent.objects.filter(name="kitchen.item.bumped").count() == 1
    assert LogEntry.objects.filter(action="started").count() == 1


def test_two_recalls_of_the_same_dish_recall_it_once(product):
    order = a_round(product, "Burger")
    line = order.lines[0].id
    run("kitchen.item.bump", {"ticket_id": str(line)})
    data = {"ticket_id": str(line)}
    results = at_once(
        as_cook("kitchen.item.recall", data, "marta"),
        as_cook("kitchen.item.recall", data, "luis"),
    )
    assert failures(results) == []
    assert TicketItem.objects.get(pk=line).status == "preparing"
    assert LogEntry.objects.filter(action="item_recalled").count() == 1
    assert LogEntry.objects.filter(action="recalled").count() == 1


def test_two_writes_finding_the_same_round_not_saved_save_it_once(product):
    order = a_round(product, "Burger", "Fries")
    first, second = (line.id for line in order.lines)
    results = at_once(
        as_cook(
            "kitchen.item.bump",
            {"ticket_id": str(first), "item_ids": [str(first)]},
            "marta",
        ),
        as_cook(
            "kitchen.item.bump",
            {"ticket_id": str(first), "item_ids": [str(second)]},
            "luis",
        ),
    )
    assert failures(results) == []
    ticket = Ticket.objects.get()
    assert (ticket.number, ticket.status) == (
        f"{ticket.day:%Y%m%d}-0001",
        "ready",
    )
    assert LogEntry.objects.filter(action="received").count() == 1


def test_two_sends_of_the_same_check_make_one_round(product):
    order = open_check("Table 4")
    add_line(order.id, product("Burger"))
    data = {"order_id": str(order.id)}
    results = at_once(
        as_cook("kitchen.ticket.send", data, "marta"),
        as_cook("kitchen.ticket.send", data, "luis"),
    )
    assert sorted(getattr(result, "code", "ok") for result in results) == [
        "ok",
        "sale.nothing_to_fire",
    ]
    assert Ticket.objects.count() == 1


# A product, a category or a station deleted while a write names it. A route read its product or category
# unheld: a deletion committed between that read and the write either left a route to a deleted product
# (Inventory's «Delete»: the row stays, marked deleted) or made the database refuse the write at its COMMIT
# (the Hub admin's: the row goes), a 500. The same for a station the Hub admin deletes while a route, a round
# or a ticket by hand names it. A write holds what it names, so the deletion waits for it; one already under
# way when the write reads it is not found, as one deleted before.

DELETIONS = ["operation", "row"]
#: A deletion gives up after this on a row another session holds (a real one waits for its COMMIT).
LOCK_TIMEOUT = "300ms"
#: Postgres' ``lock_not_available``: the deletion found the row held.
LOCK_NOT_AVAILABLE = "55P03"
#: How long a deletion under way holds its row before it commits.
IN_FLIGHT = 0.5
#: The business's «Delete» of each kind of row: its own app's operation and the field that names it.
DELETE_OPERATIONS = {
    Product: ("inventory.product.delete", "id"),
    Category: ("inventory.category.delete", "id"),
    Station: ("kitchen.station.delete", "station_id"),
}


def remove(target, how: str) -> None:
    if how == "operation":
        name, field = DELETE_OPERATIONS[type(target)]
        run(name, {field: str(target.pk)})
    else:
        # What the Hub admin's «Delete» does: ModelAdmin.delete_model is the row's delete().
        type(target).objects.get(pk=target.pk).delete()


def delete(target, how: str) -> None:
    """Deletes ``target`` in this session, giving up after LOCK_TIMEOUT on a row another session holds. The
    lock timeout is the transaction's (SET LOCAL): a session-level one would go back with the connection and
    reach the tests after this one."""
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
    table = f'"{type(target)._meta.db_table}"'
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


def sqlstate(error) -> str | None:
    while error is not None:
        if getattr(error, "sqlstate", None):
            return error.sqlstate
        error = error.__cause__ or error.__context__
    return None


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


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
def world(product, category):
    return SimpleNamespace(
        grill=make_station("Grill"),
        burger=Product.objects.get(pk=product("Burger").id),
        mains=Category.objects.get(pk=category("Mains").id),
    )


def routes_to(target):
    if isinstance(target, Product):
        return ProductRoute.objects.filter(product_id=target.pk)
    return CategoryRoute.objects.filter(category_id=target.pk)


def routed_while_deleted(target) -> bool:
    """A route to ``target`` while it is deleted (marked or gone): what the kitchen must never be left with."""
    live = type(target).objects.filter(pk=target.pk, is_deleted=False)
    return routes_to(target).exists() and not live.exists()


#: Each route that names a product or a category of Inventory: the call, the statement that writes it
#: down, what it names and the refusal of one deleted before.
ROUTE_WRITES = {
    "product": (
        lambda w: run("kitchen.routing.set", {"station_id": str(w.grill.id), "product_id": str(w.burger.id)}),
        'INSERT INTO "kitchen_productroute"',
        "burger",
        "kitchen.product_not_found",
    ),
    "product_by_name": (
        lambda w: run("kitchen.routing.set", {"station_id": str(w.grill.id), "product": "Burger"}),
        'INSERT INTO "kitchen_productroute"',
        "burger",
        "kitchen.product_not_found",
    ),
    "category": (
        lambda w: run("kitchen.routing.set", {"station_id": str(w.grill.id), "category_id": str(w.mains.id)}),
        'INSERT INTO "kitchen_categoryroute"',
        "mains",
        "kitchen.category_not_found",
    ),
}


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(ROUTE_WRITES))
def test_a_product_or_category_deleted_while_routed_waits_for_the_route(world, write, how):
    call, statement, name, _ = ROUTE_WRITES[write]
    target = getattr(world, name)
    with deleted_just_before(statement, target, how) as deletions:
        call(world)
    assert held(deletions), deleted(deletions)
    assert not routed_while_deleted(target)
    assert list(routes_to(target).values_list("station_id", flat=True)) == [world.grill.id]


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(ROUTE_WRITES))
def test_a_product_or_category_being_deleted_when_routed_is_not_found(world, write, how):
    call, _, name, code = ROUTE_WRITES[write]
    target = getattr(world, name)
    with deleted_in_flight(target, how) as deletions:
        outcome = attempt(lambda: call(world))
    assert deletions == ["ok"]
    # As for one deleted before: the kitchen's own refusal, which the routes screen shows.
    assert isinstance(outcome, NotFound), outcome
    assert (outcome.status, outcome.code) == (404, code)
    assert not routes_to(target).exists()


def a_fired_round(w):
    """The burger goes to the grill, and a check with a burger is fired by Sales (not saved by the kitchen)."""
    route_product(w.burger.id, w.grill)
    order = open_check("Table 4")
    add_line(order.id, w.burger)
    fire(order.id)
    return lambda: run("kitchen.ticket.sync", {}, system_context(A))


def a_ticket_by_hand(w):
    """The burger goes to the grill; a ticket by hand with a burger."""
    route_product(w.burger.id, w.grill)
    return lambda: run("kitchen.ticket.create", {"label": "Staff", "items": [{"product_id": str(w.burger.id)}]})


def a_new_route(w):
    return lambda: run("kitchen.routing.set", {"station_id": str(w.grill.id), "product_id": str(w.burger.id)})


def dish_station():
    return TicketItem.objects.get().station_id


def route_station():
    return ProductRoute.objects.get().station_id


#: Each write that names a station: how it is prepared (the call it makes), the statement that writes the
#: station down and where it lands.
STATION_WRITES = {
    "routing.set": (a_new_route, 'INSERT INTO "kitchen_productroute"', route_station),
    "round": (a_fired_round, 'INSERT INTO "kitchen_ticketitem"', dish_station),
    "ticket.create": (a_ticket_by_hand, 'INSERT INTO "kitchen_ticketitem"', dish_station),
}


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(STATION_WRITES))
def test_a_station_deleted_while_a_write_names_it_waits_for_the_write(world, write, how):
    # The kitchen's own «Delete» waits for any write of the kitchen (the settings row); the Hub admin's
    # waits for the station the write holds.
    prepare, statement, landed = STATION_WRITES[write]
    call = prepare(world)
    with deleted_just_before(statement, world.grill, how) as deletions:
        call()
    assert held(deletions), deleted(deletions)
    assert landed() == world.grill.id


def test_a_station_being_deleted_when_a_route_is_set_is_not_found(world):
    with deleted_in_flight(world.grill, "row") as deletions:
        outcome = attempt(a_new_route(world))
    assert deletions == ["ok"]
    assert isinstance(outcome, NotFound), outcome
    assert (outcome.status, outcome.code) == (404, "kitchen.station_not_found")
    assert not ProductRoute.objects.exists()


@pytest.mark.parametrize("write", ["round", "ticket.create"])
def test_a_station_being_deleted_when_a_dish_goes_to_it_leaves_the_dish_with_no_station(world, write):
    prepare, _, landed = STATION_WRITES[write]
    call = prepare(world)
    with deleted_in_flight(world.grill, "row") as deletions:
        call()
    assert deletions == ["ok"]
    assert not Station.objects.filter(pk=world.grill.pk).exists()
    # Its route went with the station: the dish goes to no station, as one routed after it was deleted.
    assert landed() is None
