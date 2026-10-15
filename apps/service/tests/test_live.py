"""Live queries of the service app: which events re-run which query after the COMMIT.

The checks (void_check, adjust_check, redeem_check) are asked at the moment of acting: not followed.
"""

from pathlib import Path

from live.live_registry import live_registry
from live.operations import get

from apps.service import events

EVENTS_SOURCE = Path(events.__file__).read_text()
SERVICE = events.SERVICE_EVENTS
CATEGORY_SHOWN = [events.CATEGORY_UPDATED, events.CATEGORY_DELETED]
STAFF = [
    "staff.member.created",
    "staff.member.updated",
    "staff.member.deactivated",
    "staff.member.terminated",
]
CUSTOMER_GONE = [
    "customer.customer.deleted",
    "customer.customer.erased",
    "customer.customer.merged",
]
CUSTOMER_NAMED = [*CUSTOMER_GONE, "customer.customer.updated"]


def service_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("service.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    assert service_queries() == {
        "service.service.list": [*SERVICE, *CATEGORY_SHOWN],
        "service.service.get": [*SERVICE, *CATEGORY_SHOWN],
        "service.service.list_for_sale": [*SERVICE, *CATEGORY_SHOWN],
        "service.catalog.status": SERVICE,
        "service.category.list": [*events.CATEGORY_EVENTS, *SERVICE],
        "service.category.get": [*events.CATEGORY_EVENTS, *SERVICE],
        "service.settings.get": [events.SETTINGS_UPDATED],
        "service.assignment.list": [*events.ASSIGNMENT_EVENTS, *SERVICE, *STAFF],
        "service.assignment.eligible": [*events.ASSIGNMENT_EVENTS, *SERVICE, *STAFF],
        "service.package.list": [
            *events.PACKAGE_EVENTS,
            events.GRANT_GRANTED,
            *SERVICE,
        ],
        "service.package.get": [*events.PACKAGE_EVENTS, events.GRANT_GRANTED, *SERVICE],
        "service.grant.list": [
            *events.GRANT_EVENTS,
            *events.SESSION_EVENTS,
            *events.PACKAGE_EVENTS,
            *CUSTOMER_NAMED,
        ],
        "service.grant.list_orphans": [
            *events.GRANT_EVENTS,
            *events.SESSION_EVENTS,
            *events.PACKAGE_EVENTS,
            *CUSTOMER_NAMED,
        ],
        "service.grant.tender_options": [
            *events.GRANT_EVENTS,
            *events.SESSION_EVENTS,
            *events.PACKAGE_EVENTS,
            *CUSTOMER_NAMED,
        ],
        "service.movement.list": [
            *events.GRANT_EVENTS,
            *events.SESSION_EVENTS,
            events.SERVICE_UPDATED,
            *CUSTOMER_NAMED,
        ],
    }


def test_every_live_query_is_a_read_with_a_permission():
    for name in service_queries():
        op = get(name)
        assert (op.kind, op.permission is not None) == ("query", True), name


def test_every_own_event_is_a_literal_of_events_py():
    for on in service_queries().values():
        for event in on:
            if event.startswith("service."):
                assert f'"{event}"' in EVENTS_SOURCE, event


def test_a_session_spent_re_runs_the_vouchers_sold_and_the_movements_but_not_the_catalog():
    affected = live_registry.affected([events.GRANT_REDEEMED])
    assert {
        "service.grant.list",
        "service.grant.list_orphans",
        "service.movement.list",
    } <= affected
    assert "service.service.list" not in affected


def test_a_professional_leaving_re_runs_who_performs_each_service():
    assert {
        "service.assignment.list",
        "service.assignment.eligible",
    } <= live_registry.affected(["staff.member.terminated"])


def test_every_step_of_a_session_of_the_till_re_runs_the_balances_and_the_options():
    for event in events.SESSION_EVENTS:
        assert {
            "service.grant.list",
            "service.grant.list_orphans",
            "service.grant.tender_options",
            "service.movement.list",
        } <= live_registry.affected([event]), event
