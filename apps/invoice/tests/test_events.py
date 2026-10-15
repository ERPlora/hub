"""The invoice app's events (``invoice.<entity>.<fact>``) and its reactions to the Sales app's events.

There is no outbox relay yet (phase 2 runs it in the worker); a reaction is tested by handing ``react``
the event as the relay will: its name, its scope and its payload. The full flows (charge → invoice,
refund → rectification, void → rectification) are in ``test_integration_sale.py``.
"""

import re

import pytest
from live.context import Scope
from live.errors import Conflict, NotFound
from live.operations import NAME_RE, registry

from apps.invoice import events
from apps.invoice.tests.conftest import deliver

A = Scope("host", "a")
PAST_FACT = re.compile(r"^invoice\.[a-z_]+\.([a-z_]+ed|paid)$")


def declared():
    return {
        name: value
        for name, value in vars(events).items()
        if name.isupper() and isinstance(value, str) and value.startswith("invoice.")
    }


def test_the_events_of_the_workbook():
    assert declared() == {
        "INVOICE_ISSUED": "invoice.invoice.issued",
        "INVOICE_RECTIFIED": "invoice.invoice.rectified",
        "INVOICE_PAID": "invoice.invoice.paid",
        "SERIES_CREATED": "invoice.series.created",
        "SERIES_UPDATED": "invoice.series.updated",
        "ISSUER_UPDATED": "invoice.issuer.updated",
    }


def test_every_event_is_app_entity_fact_in_the_past():
    for value in declared().values():
        assert NAME_RE.match(value), value
        assert PAST_FACT.match(value), value


def test_it_reacts_to_the_charge_the_refund_and_the_void_of_a_sale():
    assert events.REACTIONS == {
        "sale.sale.completed": "invoice.invoice.create_from_sale",
        "sale.sale.refunded": "invoice.invoice.rectify_from_refund",
        "sale.sale.voided": "invoice.invoice.rectify_from_void",
    }
    for operation in events.REACTIONS.values():
        assert registry[operation].kind == "command"


def test_an_event_it_does_not_react_to_is_ignored():
    assert events.react(A, "sale.order.opened", {"order_id": "x"}) is None


@pytest.mark.django_db
def test_a_reaction_runs_as_the_system_and_refuses_what_does_not_exist():
    with pytest.raises(NotFound):
        events.react(
            A,
            "sale.sale.completed",
            {"sale_id": "01999999-0000-7000-8000-000000000000", "items": []},
        )
    with pytest.raises(NotFound):
        events.react(
            A,
            "sale.sale.refunded",
            {"refund_id": "01999999-0000-7000-8000-000000000000", "sale_id": "x"},
        )


@pytest.mark.django_db
def test_a_refund_of_a_sale_without_its_invoice_waits_for_it(charge, product):
    # Charged without an issuer, the sale has no document yet (INVOICE-F06).
    product()
    charge()
    sale_id = deliver_payload("sale.sale.completed")["sale_id"]
    from apps.invoice.tests.conftest import run

    from apps.sale.models import Sale

    sale = Sale.objects.get(pk=sale_id)
    payment = sale.payments.get()
    run(
        "sale.sale.refund",
        {
            "sale_id": sale_id,
            "reason": "broken",
            "allocations": [{"payment_id": str(payment.id), "amount": 100}],
        },
    )
    # The sale has no document yet: the refund is refused so that the relay retries it later.
    with pytest.raises(Conflict) as refused:
        deliver("sale.sale.refunded")
    assert refused.value.code == "invoice.sale_not_invoiced"


def deliver_payload(name):
    from live.models import OutboxEvent

    return (
        OutboxEvent.objects.filter(name=name)
        .order_by("-created_at", "-id")
        .first()
        .payload
    )
