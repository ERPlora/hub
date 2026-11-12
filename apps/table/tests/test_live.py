"""Live queries of the table app: which events re-run which query after the COMMIT.

The floor is live (TABLE-F09): seating, moving, joining, splitting, charging or voiding in Sales and a
customer put on a check re-run the plan, the zones' free tables and the checks of the room.
"""

import pytest
from live.context import system_context
from live.live_registry import live_registry
from live.operations import get

from apps.table import events

from .conftest import A, make_customer, make_table, run

SALE = [
    "sale.order.completed",
    "sale.order.voided",
    "sale.order.merged",
    "sale.sale.completed",
    "sale.sale.voided",
]
CUSTOMER = [
    "customer.order.linked",
    "customer.order.unlinked",
    "customer.customer.updated",
    "customer.customer.erased",
    "customer.customer.deleted",
    "customer.customer.merged",
    "customer.customer.restored",
]
FLOOR = [
    *events.TABLE_EVENTS,
    *events.ZONE_EVENTS,
    *events.HOLD_EVENTS,
    *events.SESSION_EVENTS,
    *SALE,
    *CUSTOMER,
]
CHECKS = [
    *events.SESSION_EVENTS,
    *events.TABLE_EVENTS,
    *events.ZONE_EVENTS,
    *SALE,
    *CUSTOMER,
]


def table_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("table.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    assert table_queries() == {
        "table.zone.list": [
            *events.ZONE_EVENTS,
            *events.TABLE_EVENTS,
            *events.HOLD_EVENTS,
            *events.SESSION_EVENTS,
            *SALE,
        ],
        "table.zone.get": [
            *events.ZONE_EVENTS,
            *events.TABLE_EVENTS,
            *events.HOLD_EVENTS,
            *events.SESSION_EVENTS,
            *SALE,
        ],
        "table.table.list": FLOOR,
        "table.table.get": FLOOR,
        "table.session.list": CHECKS,
        "table.session.get": CHECKS,
        "table.session.by_order": CHECKS,
        "table.waiter.list": [events.SESSION_OPENED, events.SESSION_DELETED],
        "table.floor.status": [*events.TABLE_EVENTS, *events.ZONE_EVENTS],
        "table.settings.get": [events.SETTINGS_UPDATED],
    }


def test_every_live_query_is_a_read_with_a_permission():
    for name in table_queries():
        op = get(name)
        assert (op.kind, op.permission is not None) == ("query", True), name


def test_charging_a_tables_check_in_sales_re_runs_the_floor_and_the_checks():
    affected = live_registry.affected(["sale.order.completed"])
    assert {"table.table.list", "table.zone.list", "table.session.list"} <= affected


def test_a_hold_re_runs_the_floor_but_not_the_checks():
    affected = live_registry.affected([events.TABLE_HELD])
    assert "table.table.list" in affected
    assert "table.session.list" not in affected


@pytest.mark.django_db
def test_a_card_recovered_from_the_separate_copy_is_named_again_on_its_check_and_repaints_the_room():
    """hub#1324: deleting a card takes her name off the check she sits at; the same card back (CUSTOMER-F33, run as
    the system from the separate copy) puts it back, and an open plan or room repaints at once, as with a deletion."""
    ana = make_customer("Ana García")
    table = make_table("1")
    run("table.session.open", {"table_id": str(table.id), "guests_count": 2, "customer_id": str(ana.id)})
    run("customer.customer.delete", {"id": str(ana.id)}, system_context(A))
    [check] = run("table.table.get", {"id": str(table.id)}).checks
    assert check.customer_name is None
    run("customer.customer.restore", {"id": str(ana.id)}, system_context(A))
    [check] = run("table.table.get", {"id": str(table.id)}).checks
    assert (check.customer_id, check.customer_name) == (ana.id, "Ana García")
    assert live_registry.affected(["customer.customer.restored"]) >= {
        "table.table.list",
        "table.table.get",
        "table.session.list",
        "table.session.get",
        "table.session.by_order",
    }
