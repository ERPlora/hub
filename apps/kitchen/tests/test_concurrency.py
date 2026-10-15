"""Two cooks at once (KITCHEN-F11, F12): real sessions in threads, real row locks.

Two cooks marking the same dish ready at the same instant mark it once (one History line, one event); two
recalls of the same dish, once; two writes that both find a round not saved yet save it once, with one
number; two sends of the same check, one round.
"""

import threading

import pytest
from django.db import connection
from live.errors import OperationError
from live.models import OutboxEvent

from apps.kitchen.models import LogEntry, Ticket, TicketItem

from .conftest import add_line, ctx_for, fire, open_check, run

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
