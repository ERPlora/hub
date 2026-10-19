"""Two cooks at once (KITCHEN-F11, F12): real sessions in threads, real row locks.

Two cooks marking the same dish ready at the same instant mark it once (one History line, one event); two
recalls of the same dish, once; two writes that both find a round not saved yet save it once, with one
number; two sends of the same check, one round. A product, a category or a station deleted while a write
names it either waits for the write or refuses it as one deleted before, never a 500, a deadlock nor a route
to a deleted product. A station or a ticket deleted while a command finds it is waited for or not found, and
one deleted while the kitchen saves what Sales did or receives a round is left as it is, never a 500.
"""

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from django.contrib.admin import site
from django.db import connection, transaction
from django.test import RequestFactory
from django.utils import timezone
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
from apps.kitchen.queries import STATION_NOT_FOUND, TICKET_NOT_FOUND

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


# A product, a category or a station deleted while a write names it (FIX-KITCHEN-ROUTE-PRODUCT-RACE). A route
# read its product or category unheld: a deletion committed between that read and the write either left a route
# to a deleted product (Inventory's «Delete»: the row stays, marked deleted) or made the database refuse the
# write at its COMMIT (the Hub admin's: the row goes), a 500. The same for a station the Hub admin deleted while
# a route, a round or a ticket by hand named it. The Hub admin's «Delete» (Django's collector) takes the rows
# that point at the row first and the row last, so a write that held the row and then locked those rows made a
# circle (a deadlock, review of hub#61): a route locks the route it replaces before it holds its product or
# category, and the Hub admin's «Delete» of a station goes in line with the kitchen's writes.

#: The business's «Delete» (its own app's operation) and the Hub admin's, by the registered ModelAdmin as its
#: delete page (``delete_model``) or its bulk action (``delete_queryset``) does.
DELETIONS = ["operation", "admin"]
STATION_DELETIONS = ["operation", "admin", "admin_bulk"]
#: A deletion gives up after this on a row another session holds (a real one waits for its COMMIT).
LOCK_TIMEOUT = "300ms"
#: Postgres' ``lock_not_available``: the deletion found the row held.
LOCK_NOT_AVAILABLE = "55P03"
#: How long a deletion under way keeps what it took before it commits.
IN_FLIGHT = 0.5
#: How long a write lets the Hub admin's «Delete» run until it ends or waits for the write.
ADMIN_REACHES_ITS_WAIT = 0.7
#: The business's «Delete» of each kind of row: its own app's operation and the field that names it.
DELETE_OPERATIONS = {
    Product: ("inventory.product.delete", "id"),
    Category: ("inventory.category.delete", "id"),
    Station: ("kitchen.station.delete", "station_id"),
    Ticket: ("kitchen.ticket.delete", "ticket_id"),
}


def remove(target, how: str) -> None:
    model = type(target)
    if how == "operation":
        name, field = DELETE_OPERATIONS[model]
        run(name, {field: str(target.pk)})
        return
    model_admin = site._registry[model]
    request = RequestFactory().post("/admin/")
    if how == "admin":
        model_admin.delete_model(request, model.objects.get(pk=target.pk))
    elif how == "admin_mark":
        # The Hub admin's change page with «is deleted» ticked: the row stays, marked deleted.
        row = model.objects.get(pk=target.pk)
        row.is_deleted, row.deleted_at = True, timezone.now()
        model_admin.save_model(request, row, None, True)
    else:
        model_admin.delete_queryset(request, model.objects.filter(pk=target.pk))


def delete(target, how: str) -> None:
    """Deletes ``target`` in this session (in a transaction, as the admin's delete page), giving up after
    LOCK_TIMEOUT on a row another session holds. The lock timeout is the transaction's (SET LOCAL): a
    session-level one would go back with the connection and reach the tests after this one."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        remove(target, how)


@contextmanager
def deleted_just_before(statement: str | Callable[[str], bool], target, how: str):
    """Deletes ``target`` in another session right before the first statement of this one that starts with
    ``statement`` (or that ``statement`` accepts: the write that names it, the lock on the row it found):
    between the read that found it and that statement, every time. It commits, or waits for this session
    when it holds the row or goes in line with the kitchen's writes (and gives up)."""
    deletions: list = []
    accepts = statement if callable(statement) else lambda sql: sql.lstrip().startswith(statement)

    def wrapper(execute, sql, params, many, context):
        if not deletions and accepts(sql):
            deletions.extend(at_once(lambda: delete(target, how)))
        return execute(sql, params, many, context)

    with connection.execute_wrapper(wrapper):
        yield deletions


@contextmanager
def deleted_in_flight(target, how: str, when: str | None = None):
    """A deletion of ``target`` under way in another session when this one first reads the table ``when`` (by
    default the target's): it has deleted it, keeping what it took, and commits a moment later while this one
    goes on."""
    table = when or f'"{type(target)._meta.db_table}"'
    under_way = threading.Event()
    deletions: list = []

    def deletion():
        try:
            with transaction.atomic():
                remove(target, how)
                under_way.set()
                time.sleep(IN_FLIGHT)
            deletions.append("ok")
        except Exception as error:  # reported to the test, which fails on it
            deletions.append(repr(error))
        finally:
            under_way.set()
            connection.close()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, context):
        if thread.ident is None and sql.lstrip().upper().startswith("SELECT") and table in sql:
            thread.start()
            under_way.wait(5)
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(wrapper):
            yield deletions
    finally:
        if thread.ident is not None:
            thread.join(30)


@contextmanager
def admin_deletes_around(statement, target, moment: str, how: str = "admin"):
    """The Hub admin deletes ``target`` (as its delete page, or ``how="admin_bulk"`` as «Delete selected»; no lock
    timeout: a deadlock is what Postgres reports) in another session, started right ``before`` or ``after`` the
    first statement of this one that ``statement`` accepts, and given ADMIN_REACHES_ITS_WAIT to end or to wait
    for this one."""
    deletions: list = []

    def deletion():
        try:
            with transaction.atomic():
                remove(target, how)
            deletions.append("ok")
        except Exception as error:  # a deadlock, reported to the test
            deletions.append(repr(error))
        finally:
            connection.close()

    thread = threading.Thread(target=deletion)

    def start():
        thread.start()
        time.sleep(ADMIN_REACHES_ITS_WAIT)

    def wrapper(execute, sql, params, many, context):
        first = thread.ident is None and statement(sql)
        if first and moment == "before":
            start()
        result = execute(sql, params, many, context)
        if first and moment == "after":
            start()
        return result

    try:
        with connection.execute_wrapper(wrapper):
            yield deletions
    finally:
        if thread.ident is not None:
            thread.join(30)
        assert thread.ident is not None, "the write never reached the statement the deletion waits for"


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


def answered(call):
    """What ``call`` answers, a 500 included (a deadlock is one): never raised, so the deletion can end."""
    try:
        return call()
    except Exception as error:
        return error


@pytest.fixture
def world(product, category):
    return SimpleNamespace(
        grill=make_station("Grill"),
        bar=make_station("Bar"),
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


def route_burger(w):
    return lambda: run("kitchen.routing.set", {"station_id": str(w.grill.id), "product_id": str(w.burger.id)})


def reroute_burger(w):
    """The burger went to the bar; now it goes to the grill (its route is replaced)."""
    route_product(w.burger.id, w.bar)
    return route_burger(w)


def route_burger_by_name(w):
    return lambda: run("kitchen.routing.set", {"station_id": str(w.grill.id), "product": "Burger"})


def route_mains(w):
    return lambda: run("kitchen.routing.set", {"station_id": str(w.grill.id), "category_id": str(w.mains.id)})


def reroute_mains(w):
    from .conftest import route_category

    route_category(w.mains.id, w.bar)
    return route_mains(w)


#: Each route that names a product or a category of Inventory: how it is prepared (the call it makes), the
#: statement that writes it down, what it names and the refusal of one deleted before.
ROUTE_WRITES = {
    "product": (route_burger, 'INSERT INTO "kitchen_productroute"', "burger", "kitchen.product_not_found"),
    "product_by_name": (
        route_burger_by_name,
        'INSERT INTO "kitchen_productroute"',
        "burger",
        "kitchen.product_not_found",
    ),
    "product_replaced": (reroute_burger, 'UPDATE "kitchen_productroute"', "burger", "kitchen.product_not_found"),
    "category": (route_mains, 'INSERT INTO "kitchen_categoryroute"', "mains", "kitchen.category_not_found"),
    "category_replaced": (
        reroute_mains,
        'UPDATE "kitchen_categoryroute"',
        "mains",
        "kitchen.category_not_found",
    ),
}


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(ROUTE_WRITES))
def test_a_product_or_category_deleted_while_routed_waits_for_the_route(world, write, how):
    prepare, statement, name, _ = ROUTE_WRITES[write]
    target = getattr(world, name)
    call = prepare(world)
    with deleted_just_before(statement, target, how) as deletions:
        call()
    assert held(deletions), deleted(deletions)
    assert not routed_while_deleted(target)
    assert list(routes_to(target).values_list("station_id", flat=True)) == [world.grill.id]


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("write", sorted(ROUTE_WRITES))
def test_a_product_or_category_being_deleted_when_routed_is_not_found(world, write, how):
    prepare, _, name, code = ROUTE_WRITES[write]
    target = getattr(world, name)
    call = prepare(world)
    with deleted_in_flight(target, how) as deletions:
        outcome = attempt(call)
    assert deletions == ["ok"]
    # As for one deleted before: the kitchen's own refusal, which the routes screen shows.
    assert isinstance(outcome, NotFound), outcome
    assert (outcome.status, outcome.code) == (404, code)
    # Not routed anew: a route it had stays as Inventory's «Delete» leaves it (one of a deleted product no
    # longer counts), or went with the Hub admin's.
    assert not routes_to(target).filter(station=world.grill).exists()


def locks_the_route(sql: str) -> bool:
    return '"kitchen_productroute"' in sql and "FOR UPDATE" in sql


def reads_the_route(sql: str) -> bool:
    return sql.lstrip().upper().startswith("SELECT") and '"kitchen_productroute"' in sql


@pytest.mark.parametrize("moment", ["before", "after"])
def test_replacing_a_route_while_the_hub_admin_deletes_its_product_is_no_deadlock(world, moment):
    route_product(world.burger.id, world.bar)
    with admin_deletes_around(locks_the_route, world.burger, moment) as deletions:
        outcome = answered(route_burger(world))
    assert deletions == ["ok"]
    assert not isinstance(outcome, Exception) or isinstance(outcome, OperationError), outcome
    assert not Product.objects.filter(pk=world.burger.pk).exists()
    assert not routes_to(world.burger).exists()


@pytest.mark.parametrize("moment", ["before", "after"])
def test_clearing_a_route_while_the_hub_admin_deletes_its_product_is_no_deadlock(world, moment):
    route_product(world.burger.id, world.grill)
    clear = lambda: run("kitchen.routing.clear", {"product_id": str(world.burger.id)})  # noqa: E731
    with admin_deletes_around(reads_the_route, world.burger, moment) as deletions:
        outcome = answered(clear)
    assert deletions == ["ok"]
    # Cleared before the deletion, or not found once it ended: never a 500.
    assert not isinstance(outcome, Exception) or isinstance(outcome, OperationError), outcome
    assert not routes_to(world.burger).exists()


def test_marking_a_dish_ready_while_the_hub_admin_deletes_its_station_is_no_deadlock(world):
    route_product(world.burger.id, world.grill)
    ticket = run("kitchen.ticket.create", {"label": "Staff", "items": [{"product_id": str(world.burger.id)}]})

    def locks_the_dishes(sql):
        return '"kitchen_ticketitem"' in sql and "FOR UPDATE" in sql

    with admin_deletes_around(locks_the_dishes, world.grill, "before") as deletions:
        outcome = answered(lambda: run("kitchen.item.bump", {"ticket_id": str(ticket.id)}))
    assert deletions == ["ok"]
    assert not isinstance(outcome, Exception), outcome
    assert TicketItem.objects.get().status == "ready"
    # The admin's «Delete» went after the cook's: the History line it left lost its station with it.
    assert LogEntry.objects.filter(item__isnull=False).get().station_id is None


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


def dish_station():
    return TicketItem.objects.get().station_id


def route_station():
    return ProductRoute.objects.get().station_id


#: Each write that names a station: how it is prepared (the call it makes), the statement that writes the
#: station down and where it lands.
STATION_WRITES = {
    "routing.set": (route_burger, 'INSERT INTO "kitchen_productroute"', route_station),
    "round": (a_fired_round, 'INSERT INTO "kitchen_ticketitem"', dish_station),
    "ticket.create": (a_ticket_by_hand, 'INSERT INTO "kitchen_ticketitem"', dish_station),
}
#: Every write of the kitchen starts by locking its settings row: a deletion that goes in line is under way
#: when the write reaches it.
IN_LINE = '"kitchen_kitchensettings"'


@pytest.mark.parametrize("how", STATION_DELETIONS)
@pytest.mark.parametrize("write", sorted(STATION_WRITES))
def test_a_station_deleted_while_a_write_names_it_waits_for_the_write(world, write, how):
    # The kitchen's own «Delete» and the Hub admin's go in line with every write of the kitchen.
    prepare, statement, landed = STATION_WRITES[write]
    call = prepare(world)
    with deleted_just_before(statement, world.grill, how) as deletions:
        call()
    assert held(deletions), deleted(deletions)
    assert landed() == world.grill.id


@pytest.mark.parametrize("how", ["admin", "admin_bulk"])
def test_a_station_being_deleted_when_a_route_is_set_is_not_found(world, how):
    with deleted_in_flight(world.grill, how, when=IN_LINE) as deletions:
        outcome = attempt(route_burger(world))
    assert deletions == ["ok"]
    assert isinstance(outcome, NotFound), outcome
    assert (outcome.status, outcome.code) == (404, "kitchen.station_not_found")
    assert not ProductRoute.objects.exists()


@pytest.mark.parametrize("write", ["round", "ticket.create"])
def test_a_station_being_deleted_when_a_dish_goes_to_it_leaves_the_dish_with_no_station(world, write):
    prepare, _, landed = STATION_WRITES[write]
    call = prepare(world)
    with deleted_in_flight(world.grill, "admin", when=IN_LINE) as deletions:
        call()
    assert deletions == ["ok"]
    assert not Station.objects.filter(pk=world.grill.pk).exists()
    # Its route went with the station: the dish goes to no station, as one routed after it was deleted.
    assert landed() is None


# A station or a ticket deleted while a command finds it (FIX-KITCHEN-STATION-DELETE-RACE). A command found its
# station or its ticket and then locked it again by its id: one gone between the two reads (the Hub admin's
# «Delete» of a ticket did not go in line with the kitchen's writes) raised DoesNotExist, a 500, and one marked
# deleted meanwhile (the Hub admin's change page) was changed, printed or deleted again as if it were live. Locked,
# a row deleted since it was found is not found, as one deleted before. The kitchen's own «Delete» and the Hub
# admin's «Delete» of a station or a ticket go in line with every write of the kitchen: they wait for it instead.

#: Who takes a station or a ticket away while a command finds it: the ones that go in line with the kitchen's
#: writes (``locked_settings``) wait for it; the Hub admin's change page comes between its two reads.
IN_LINE_DELETIONS = {Station: ["operation", "admin", "admin_bulk"], Ticket: ["operation", "admin", "admin_bulk"]}
BETWEEN_THE_READS = {Station: ["admin_mark"], Ticket: ["admin_mark"]}


def locks(table: str) -> Callable[[str], bool]:
    """The statement that locks a row of ``table`` it found (``SELECT … FOR UPDATE``)."""
    return lambda sql: f'"{table}"' in sql and "FOR UPDATE" in sql


def not_found(outcome, code: str, message) -> None:
    """``outcome`` is the kitchen's own 404, as for one deleted before: its code and its message, never a 500."""
    assert isinstance(outcome, NotFound), outcome
    assert (outcome.status, outcome.code, outcome.message) == (404, code, str(message))


#: Each command on a station: what it is sent, and what it leaves when it goes through.
ON_A_STATION = {
    "station.update": (
        lambda station: {"station_id": str(station.id), "name": "Hot line"},
        lambda station: Station.objects.get(pk=station.pk).name == "Hot line",
    ),
    "station.delete": (
        lambda station: {"station_id": str(station.id)},
        lambda station: Station.objects.get(pk=station.pk).is_deleted,
    ),
}


@pytest.mark.parametrize("how", IN_LINE_DELETIONS[Station])
@pytest.mark.parametrize("command", sorted(ON_A_STATION))
def test_a_station_deleted_in_line_while_a_command_finds_it_waits_for_the_command(world, command, how):
    sent, went_through = ON_A_STATION[command]
    with deleted_just_before(locks("kitchen_station"), world.grill, how) as deletions:
        outcome = attempt(lambda: run(f"kitchen.{command}", sent(world.grill)))
    assert held(deletions), deleted(deletions)
    assert not isinstance(outcome, OperationError), outcome
    assert went_through(world.grill)


@pytest.mark.parametrize("how", BETWEEN_THE_READS[Station])
@pytest.mark.parametrize("command", sorted(ON_A_STATION))
def test_a_station_deleted_while_a_command_finds_it_is_not_found(world, command, how):
    sent, _ = ON_A_STATION[command]
    recorded = OutboxEvent.objects.count()
    with deleted_just_before(locks("kitchen_station"), world.grill, how) as deletions:
        outcome = attempt(lambda: run(f"kitchen.{command}", sent(world.grill)))
    assert deleted(deletions) == ["ok"]
    not_found(outcome, "kitchen.station_not_found", STATION_NOT_FOUND)
    # Left as the Hub admin left it, and nothing of the refused command: the Hub admin records no event.
    assert Station.objects.filter(pk=world.grill.pk).values_list("name", "is_deleted").get() == ("Grill", True)
    assert OutboxEvent.objects.count() == recorded


def a_ticket(w, *then: str) -> Ticket:
    """A ticket by hand with a burger, moved on by the kitchen's commands ``then``."""
    ticket = run("kitchen.ticket.create", {"label": "Staff", "items": [{"product_id": str(w.burger.id)}]})
    for name in then:
        run(name, {"ticket_id": str(ticket.id)})
    return Ticket.objects.get(pk=ticket.id)


#: Each command on a ticket: the commands that bring a new ticket to where it applies, and what else it is sent.
ON_A_TICKET = {
    "ticket.start": ((), {}),
    "ticket.ready": ((), {}),
    "ticket.serve": (("kitchen.ticket.ready",), {}),
    "ticket.recall": (("kitchen.ticket.ready",), {}),
    "ticket.cancel": ((), {"reason": "Cold"}),
    "ticket.delete": ((), {}),
    "ticket.set_rush": ((), {"rush": True}),
    "ticket.reprint": ((), {}),
    "item.bump": ((), {}),
    "item.recall": (("kitchen.item.bump",), {}),
}


@pytest.mark.parametrize("how", IN_LINE_DELETIONS[Ticket])
@pytest.mark.parametrize("command", sorted(ON_A_TICKET))
def test_a_ticket_deleted_in_line_while_a_command_finds_it_waits_for_the_command(world, command, how):
    then, more = ON_A_TICKET[command]
    ticket = a_ticket(world, *then)
    with deleted_just_before(locks("kitchen_ticket"), ticket, how) as deletions:
        outcome = attempt(lambda: run(f"kitchen.{command}", {"ticket_id": str(ticket.id), **more}))
    assert held(deletions), deleted(deletions)
    # Not refused as gone: it went through, or was refused for its own reason (a reprint with no printer).
    assert getattr(outcome, "code", None) != "kitchen.ticket_not_found", outcome


def state(ticket_id) -> tuple:
    """What a command changes on a ticket: its state, priority and copies, its dishes' states, its History."""
    ticket = Ticket.objects.get(pk=ticket_id)
    return (
        ticket.status,
        ticket.priority,
        ticket.reprint_count,
        list(ticket.items.order_by("position").values_list("status", flat=True)),
        ticket.log.count(),
    )


def left_as_the_admin_left_it(ticket_id, before: tuple) -> None:
    """Marked deleted by the Hub admin's change page, with nothing else changed."""
    assert Ticket.objects.get(pk=ticket_id).is_deleted
    assert state(ticket_id) == before


@pytest.mark.parametrize("how", BETWEEN_THE_READS[Ticket])
@pytest.mark.parametrize("command", sorted(ON_A_TICKET))
def test_a_ticket_deleted_while_a_command_finds_it_is_not_found(world, command, how):
    then, more = ON_A_TICKET[command]
    ticket = a_ticket(world, *then)
    before = state(ticket.pk)
    recorded = OutboxEvent.objects.count()
    with deleted_just_before(locks("kitchen_ticket"), ticket, how) as deletions:
        outcome = attempt(lambda: run(f"kitchen.{command}", {"ticket_id": str(ticket.id), **more}))
    assert deleted(deletions) == ["ok"]
    not_found(outcome, "kitchen.ticket_not_found", TICKET_NOT_FOUND)
    left_as_the_admin_left_it(ticket.pk, before)
    # Nothing of the refused command: the Hub admin records no event.
    assert OutboxEvent.objects.count() == recorded


@pytest.mark.parametrize("named", ["by its id", "by its number", "by its label"])
def test_a_ticket_named_by_a_person_and_deleted_while_it_is_found_is_not_found(world, named):
    ticket = a_ticket(world)
    ref = {"by its id": {"ticket_id": str(ticket.id)}, "by its number": {"ticket": ticket.number}}.get(
        named, {"ticket": ticket.label}
    )
    with deleted_just_before(locks("kitchen_ticket"), ticket, "admin_mark") as deletions:
        outcome = attempt(lambda: run("kitchen.ticket.start", ref))
    assert deleted(deletions) == ["ok"]
    not_found(outcome, "kitchen.ticket_not_found", TICKET_NOT_FOUND)


def a_round_sales_voids(w) -> Ticket:
    """A round of a check, saved by the kitchen, whose only line Sales then voids: the kitchen's next write
    saves that its ticket is cancelled."""
    order = open_check("Table 4")
    add_line(order.id, w.burger)
    run("kitchen.ticket.send", {"order_id": str(order.id)})
    ticket = Ticket.objects.get()
    line = ticket.items.get().sale_line_id
    run("sale.order.void_line", {"order_id": str(order.id), "line_id": str(line), "reason": "Cold"})
    return ticket


@pytest.mark.parametrize("how", ["admin", "admin_bulk"])
def test_the_hub_admin_deleting_a_ticket_while_the_kitchen_saves_what_sales_did_waits_for_it(world, how):
    ticket = a_round_sales_voids(world)
    with deleted_just_before(locks("kitchen_ticket"), ticket, how) as deletions:
        outcome = attempt(lambda: run("kitchen.ticket.sync", {}, system_context(A)))
    assert held(deletions), deleted(deletions)
    assert (outcome.received, outcome.changed) == (0, 1)
    assert Ticket.objects.get(pk=ticket.pk).status == "cancelled"


@pytest.mark.parametrize("how", BETWEEN_THE_READS[Ticket])
def test_a_ticket_deleted_while_the_kitchen_saves_what_sales_did_is_left_alone(world, how):
    # Every write of the kitchen starts by saving what Sales did to the tickets on the line: one the Hub admin
    # deleted meanwhile is not saved again, and the write goes on.
    ticket = a_round_sales_voids(world)
    before = state(ticket.pk)
    with deleted_just_before(locks("kitchen_ticket"), ticket, how) as deletions:
        outcome = attempt(lambda: run("kitchen.ticket.sync", {}, system_context(A)))
    assert deleted(deletions) == ["ok"]
    assert not isinstance(outcome, OperationError), outcome
    assert (outcome.received, outcome.changed) == (0, 0)
    left_as_the_admin_left_it(ticket.pk, before)


def a_round_saved(w) -> tuple[Ticket, dict]:
    """A round fired by Sales and saved by the kitchen, and the reaction to its send (``kitchen.ticket.receive``)."""
    order = open_check("Table 4")
    add_line(order.id, w.burger)
    fire(order.id)
    run("kitchen.ticket.sync", {}, system_context(A))
    ticket = Ticket.objects.get()
    return ticket, {"order_id": str(order.id), "round_no": ticket.round_no, "priority": "rush", "waiter": "luis"}


@pytest.mark.parametrize("how", ["admin", "admin_bulk"])
def test_the_hub_admin_deleting_a_ticket_while_its_round_is_received_waits_for_it(world, how):
    ticket, data = a_round_saved(world)
    with deleted_just_before(locks("kitchen_ticket"), ticket, how) as deletions:
        outcome = attempt(lambda: run("kitchen.ticket.receive", data, system_context(A)))
    assert held(deletions), deleted(deletions)
    assert (outcome.ticket.id, outcome.ticket.priority) == (ticket.id, "rush")


@pytest.mark.parametrize("how", BETWEEN_THE_READS[Ticket])
def test_a_ticket_deleted_while_its_round_is_received_is_not_received(world, how):
    # The reaction to a round sent: its ticket, saved before, gets the send's priority, label and waiter and
    # goes to paper. One the Hub admin marked deleted meanwhile is not received, as one deleted before.
    ticket, data = a_round_saved(world)
    before = state(ticket.pk)
    with deleted_just_before(locks("kitchen_ticket"), ticket, how) as deletions:
        outcome = attempt(lambda: run("kitchen.ticket.receive", data, system_context(A)))
    assert deleted(deletions) == ["ok"]
    assert not isinstance(outcome, OperationError), outcome
    assert outcome.ticket is None
    left_as_the_admin_left_it(ticket.pk, before)


# The Hub admin's «Delete» of a ticket a cook is working on (FIX-KITCHEN-STATION-DELETE-RACE). Django's collector
# takes a ticket's History and dishes first and the ticket last, while a cook's command holds the ticket and then
# its dishes and writes its History: out of line, the two waited for each other in a circle (a deadlock, 40P01) or
# the ticket went while the cook's new History line named it (the FK refused the deletion at its end). In line
# with the kitchen's writes (``locked_settings`` → ticket, as the operations take them), the «Delete» waits for the
# cook and then takes what the cook added; started first, the cook waits for it and hears the ticket is gone.


def locks_the_dishes(sql: str) -> bool:
    return '"kitchen_ticketitem"' in sql and "FOR UPDATE" in sql


def writes_the_history(sql: str) -> bool:
    return sql.lstrip().startswith('INSERT INTO "kitchen_logentry"')


#: Each command of a cook on a ticket, and a statement it runs while it holds the ticket.
COOK_ON_A_TICKET = {
    "item.bump": ("kitchen.item.bump", locks_the_dishes),
    "ticket.start": ("kitchen.ticket.start", writes_the_history),
}


@pytest.mark.parametrize("order", ["cook first, admin before", "cook first, admin after", "admin first"])
@pytest.mark.parametrize("how", ["admin", "admin_bulk"])
@pytest.mark.parametrize("command", sorted(COOK_ON_A_TICKET))
def test_the_hub_admin_deleting_a_ticket_a_cook_works_on_is_no_deadlock(world, command, how, order):
    name, statement = COOK_ON_A_TICKET[command]
    ticket = a_ticket(world)
    if order == "admin first":
        deleting = deleted_in_flight(ticket, how, when=IN_LINE)
    else:
        deleting = admin_deletes_around(statement, ticket, order.rsplit(" ", 1)[1], how)
    with deleting as deletions:
        outcome = answered(lambda: run(name, {"ticket_id": str(ticket.id)}))
    # No deadlock nor a refused deletion: the «Delete» ended, and the ticket went with all it had.
    assert deletions == ["ok"], deletions
    assert not Ticket.objects.filter(pk=ticket.pk).exists()
    assert not LogEntry.objects.filter(ticket_id=ticket.pk).exists()
    if order == "admin first":
        not_found(outcome, "kitchen.ticket_not_found", TICKET_NOT_FOUND)
    else:
        assert not isinstance(outcome, Exception), outcome
