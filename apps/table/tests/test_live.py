"""Live queries of the table app: which events re-run which query after the COMMIT.

The floor is live (TABLE-F09): seating, moving, joining, splitting, charging or voiding in Sales and a
customer put on a check re-run the plan, the zones' free tables and the checks of the room.
"""

from live.live_registry import live_registry
from live.operations import get

from apps.table import events

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
