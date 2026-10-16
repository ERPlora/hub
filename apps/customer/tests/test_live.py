"""Live queries of the customer app: which events re-run which query after the COMMIT."""

import re
from pathlib import Path

from live.live_registry import live_registry

from apps.customer import events, services

E = events
SERVICES_SOURCE = Path(services.__file__).read_text()
CARD_GONE = [E.CUSTOMER_DELETED, E.CUSTOMER_MERGED, E.CUSTOMER_ERASED]

EXPECTED = {
    "customer.customer.list": [
        E.CUSTOMER_CREATED,
        E.CUSTOMER_UPDATED,
        *CARD_GONE,
        E.PURCHASE_RECORDED,
        E.PURCHASE_VOIDED,
        E.PURCHASE_REFUNDED,
    ],
    "customer.customer.detail": [
        E.CUSTOMER_UPDATED,
        E.CUSTOMER_GROUPS_CHANGED,
        E.CUSTOMER_TAGS_CHANGED,
        *CARD_GONE,
        E.CONSENT_GRANTED,
        E.CONSENT_WITHDRAWN,
        E.PURCHASE_RECORDED,
        E.PURCHASE_VOIDED,
        E.PURCHASE_REFUNDED,
        E.GROUP_DELETED,
        E.TAG_DELETED,
        E.FIELD_CREATED,
        E.FIELD_UPDATED,
        E.FIELD_DELETED,
    ],
    "customer.customer.stats": [
        E.CUSTOMER_CREATED,
        E.CUSTOMER_UPDATED,
        *CARD_GONE,
        E.PURCHASE_RECORDED,
        E.PURCHASE_VOIDED,
        E.PURCHASE_REFUNDED,
    ],
    "customer.group.list": [
        E.GROUP_CREATED,
        E.GROUP_UPDATED,
        E.GROUP_DELETED,
        E.CUSTOMER_GROUPS_CHANGED,
        *CARD_GONE,
    ],
    "customer.tag.list": [
        E.TAG_CREATED,
        E.TAG_UPDATED,
        E.TAG_DELETED,
        E.CUSTOMER_TAGS_CHANGED,
        *CARD_GONE,
    ],
    "customer.field.list": [E.FIELD_CREATED, E.FIELD_UPDATED, E.FIELD_DELETED],
    "customer.activity.list": [
        E.NOTE_ADDED,
        E.ACTIVITY_RECORDED,
        E.CONSENT_GRANTED,
        E.CONSENT_WITHDRAWN,
        E.PURCHASE_RECORDED,
        E.PURCHASE_VOIDED,
        E.PURCHASE_REFUNDED,
        E.HEALTH_CONSENT_GRANTED,
        E.HEALTH_CONSENT_WITHDRAWN,
        E.HEALTH_UPDATED,
        *CARD_GONE,
    ],
    "customer.purchase.list": [E.PURCHASE_RECORDED, E.PURCHASE_VOIDED, E.PURCHASE_REFUNDED, *CARD_GONE],
    "customer.purchase.divergences": [
        E.PURCHASE_RECORDED,
        E.PURCHASE_VOIDED,
        E.PURCHASE_REFUNDED,
        *CARD_GONE,
    ],
    "customer.consent.state": [
        E.CONSENT_GRANTED,
        E.CONSENT_WITHDRAWN,
        E.HEALTH_CONSENT_GRANTED,
        E.HEALTH_CONSENT_WITHDRAWN,
        *CARD_GONE,
    ],
    "customer.consent.history": [
        E.CONSENT_GRANTED,
        E.CONSENT_WITHDRAWN,
        E.HEALTH_CONSENT_GRANTED,
        E.HEALTH_CONSENT_WITHDRAWN,
        *CARD_GONE,
    ],
    "customer.order.customer": [E.ORDER_LINKED, E.ORDER_UNLINKED, *CARD_GONE],
    "customer.order.list": [E.ORDER_LINKED, E.ORDER_UNLINKED, *CARD_GONE],
    "customer.health.detail": [
        E.HEALTH_CONSENT_GRANTED,
        E.HEALTH_CONSENT_WITHDRAWN,
        E.HEALTH_UPDATED,
        *CARD_GONE,
    ],
}


def customer_queries():
    return {
        name: on
        for name, on in live_registry.subscribable.items()
        if name.startswith("customer.")
    }


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_each_live_query_and_its_events():
    assert customer_queries() == EXPECTED


def test_the_lookup_by_phone_and_the_export_are_not_live():
    # One-off reads: the till asks by_phone once, and the export is a file, not a screen.
    assert {"customer.customer.by_phone", "customer.customer.export"}.isdisjoint(
        customer_queries()
    )


def test_every_cited_event_is_recorded_by_a_service():
    recorded = set(re.findall(r"events\.([A-Z_]+)", SERVICES_SOURCE))
    for on in customer_queries().values():
        for event in on:
            assert event in events.ALL, event
            name = next(
                constant for constant, value in vars(events).items() if value == event
            )
            assert name in recorded, event


def test_every_event_re_runs_some_query():
    cited = {event for on in customer_queries().values() for event in on}
    assert set(events.ALL) == cited


def test_a_note_re_runs_the_timeline_but_not_the_card():
    affected = live_registry.affected([E.NOTE_ADDED])
    assert (
        "customer.activity.list" in affected
        and "customer.customer.detail" not in affected
    )
