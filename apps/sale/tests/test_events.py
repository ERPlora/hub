"""The sale app's events (``sale.<entity>.<fact>``) and its reaction to Customers' merge.

There is no outbox relay yet (phase 2 runs it in the worker); a reaction is tested by handing ``react``
the event as the relay will: its name, its scope and its payload.
"""

import re

import pytest
from live.context import Scope
from live.operations import NAME_RE

from apps.sale import events
from apps.sale.models import Sale
from apps.sale.tests.conftest import run

PAST_FACT = re.compile(r"^sale\.[a-z_]+\.[a-z_]+(ed|_from_appointment)$")
A = Scope("host", "a")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("sale.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "SALE_COMPLETED": "sale.sale.completed",
        "SALE_CREATED_FROM_APPOINTMENT": "sale.sale.created_from_appointment",
        "SALE_VOIDED": "sale.sale.voided",
        "SALE_REFUNDED": "sale.sale.refunded",
        "SALE_REASSIGNED": "sale.sale.reassigned",
        "ORDER_OPENED": "sale.order.opened",
        "ORDER_CHANGED": "sale.order.changed",
        "ORDER_FIRED": "sale.order.fired",
        "ORDER_COMPLETED": "sale.order.completed",
        "ORDER_VOIDED": "sale.order.voided",
        "ORDER_MERGED": "sale.order.merged",
        "ORDER_LINE_REMOVED": "sale.order.line_removed",
        "ORDER_LINE_VOIDED": "sale.order.line_voided",
        "PAYMENT_METHOD_CREATED": "sale.payment_method.created",
        "SETTINGS_UPDATED": "sale.settings.updated",
        "DEPARTMENT_CREATED": "sale.department.created",
        "DEPARTMENT_UPDATED": "sale.department.updated",
        "DEPARTMENT_DELETED": "sale.department.deleted",
        "QUICK_NOTE_CREATED": "sale.quick_note.created",
        "QUICK_NOTE_UPDATED": "sale.quick_note.updated",
        "QUICK_NOTE_DELETED": "sale.quick_note.deleted",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_all_lists_every_event_once():
    assert events.ALL == list(declared().values())


def test_it_reacts_to_two_customer_cards_merged():
    assert events.REACTIONS == {"customer.customer.merged": "sale.customer.reassign"}


def test_an_event_it_does_not_follow_is_ignored():
    assert events.react(A, "customer.customer.created", {"id": "x"}) is None


@pytest.mark.django_db
def test_the_merge_of_customer_moves_the_sales(product, customer):
    product("Coffee", "COF", 150, "product.generic")
    ana, duplicate = customer("Ana López"), customer("Ana Lopez")
    run(
        "sale.sale.complete",
        {
            "idempotency_key": "react-key-01",
            "lines": [{"product": "COF"}],
            "customer_id": str(duplicate.id),
        },
    )
    # Customers' own merge, which records the event the relay will hand over.
    run(
        "customer.customer.merge", {"id": str(ana.id), "absorbed_id": str(duplicate.id)}
    )
    from live.models import OutboxEvent

    merged = OutboxEvent.objects.get(name="customer.customer.merged")
    result = events.react(A, merged.name, merged.payload)
    assert result.moved == 1
    assert Sale.objects.get().customer_id == ana.id
