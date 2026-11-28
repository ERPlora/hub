"""A write whose event for Invoicing the relay gave up on (System › Failed events, the bell's urgent notice) gets its
document by hand afterwards (INVOICE-F06: «Issue now», the API or the assistant). That failed event goes back to the
queue at once, out of the list and the bell, and the relay then finds the document done: no other document, no other
number, no other record. Another sale's failed events, another app's, a discarded one and another business's stay as
they are.
"""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import NotFound
from live.models import OutboxEvent

from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import B, HUB_DB, ISSUER, run
from apps.sale.models.refunds import Refund
from apps.sale.models.sales import Sale
from apps.verifactu.models import Record
from base import events, relay
from base.models.relay import EventDelivery
from base.services import relay_runs
from base.tenancy.context import use_hub

#: What a test seals for the tax agency never leaves the machine.
pytestmark = [HUB_DB, pytest.mark.usefixtures("nothing_leaves")]

DEAD = EventDelivery.Status.DEAD


@pytest.fixture(autouse=True)
def shelf(product):
    product("Shampoo", "SHA", 1210, "product.generic")


def given_up(name, *, app="invoice", status=DEAD, **match):
    """The delivery to ``app`` of the ``name`` event whose payload holds ``match``, as the relay leaves it after its
    last attempt (or as who runs the business left it, ``status``)."""
    event = OutboxEvent.objects.get(name=name, payload__contains=match)
    return EventDelivery.objects.create(
        event=event,
        app_label=app,
        status=status,
        attempts=relay.MAX_ATTEMPTS,
        last_error="Conflict: Set up the issuer (Invoicing › Issuer) before issuing an invoice.",
        next_attempt_at=timezone.now() - dt.timedelta(hours=1),
    )


def failed_ids():
    """The ids of System › Failed events, and the count of the bell's urgent notice (0 without it)."""
    listed = run("base.failed_event.list", {"limit": 100})
    bell = {counter.key: counter.count for counter in run("base.bell.counters").counters}
    return {item.id for item in listed.items}, bell.get("base.failed_events", 0)


def state(delivery):
    delivery.refresh_from_db()
    return delivery.status, delivery.attempts


def relay_pass():
    """Every delivery due now, run once by the relay with the apps' real reactions."""
    for _ in range(10):
        if (
            relay_runs.relay_deliver_next(
                timezone.now(),
                deliver=relay.deliver,
                listeners=relay.listeners,
                carried=relay.carried,
                max_depth=relay.MAX_EVENT_DEPTH,
                max_attempts=relay.MAX_ATTEMPTS,
                backoff=relay.backoff,
            )
            is None
        ):
            return


@pytest.mark.parametrize(
    ("operation", "by"),
    [
        ("sale.sale.issue_documents", lambda sale: {"sale": sale.number}),
        ("invoice.invoice.create_from_sale", lambda sale: {"sale": sale.number}),
    ],
    ids=["issue-now", "invoicing-api"],
)
def test_the_sales_failed_event_leaves_the_list_and_the_bell_once_its_document_is_issued(charge, operation, by):
    sale = charge("failed-ev-0001")
    other = charge("failed-ev-0002")
    mine = given_up("sale.sale.completed", sale_id=str(sale.id))
    another_sale = given_up("sale.sale.completed", sale_id=str(other.id))
    another_app = given_up("sale.sale.completed", app="customer", sale_id=str(sale.id))
    assert failed_ids() == ({mine.id, another_sale.id, another_app.id}, 3)

    run("invoice.issuer.update", ISSUER)
    run(operation, by(sale))

    assert Sale.objects.get(pk=sale.id).invoice_status == "issued"
    assert failed_ids() == ({another_sale.id, another_app.id}, 2)
    assert state(mine) == ("pending", 0)
    assert (state(another_sale), state(another_app)) == ((DEAD, relay.MAX_ATTEMPTS), (DEAD, relay.MAX_ATTEMPTS))
    retried = OutboxEvent.objects.filter(name=events.FAILED_EVENT_RETRIED)
    assert [event.payload for event in retried] == [{"count": 1}]


def test_the_relay_then_finds_the_ticket_done_and_a_later_resend_issues_nothing(charge):
    sale = charge("failed-ev-0003")
    mine = given_up("sale.sale.completed", sale_id=str(sale.id))
    run("invoice.issuer.update", ISSUER)
    run("sale.sale.issue_documents", {"sale": sale.number})
    ticket = Invoice.objects.get(source_sale_id=sale.id)

    relay_pass()

    assert state(mine) == ("delivered", 1)
    assert Invoice.objects.filter(source_sale_id=sale.id).count() == 1
    assert Record.objects.filter(invoice_id=ticket.id).count() == 1
    assert OutboxEvent.objects.filter(name="sale.sale.invoiced", payload__sale_id=str(sale.id)).count() == 1
    with pytest.raises(NotFound):
        run("base.failed_event.retry", {"id": str(mine.id)})
    assert Invoice.objects.filter(source_sale_id=sale.id).count() == 1
    assert Sale.objects.get(pk=sale.id).invoice_number == ticket.number


def test_a_voids_failed_event_leaves_only_with_its_own_rectifying_invoice(charge):
    sale = charge("failed-ev-0004")
    run("sale.sale.void", {"sale_id": str(sale.id), "reason": "Wrong table"})
    completed = given_up("sale.sale.completed", sale_id=str(sale.id))
    voided = given_up("sale.sale.voided", sale_id=str(sale.id))
    run("invoice.issuer.update", ISSUER)

    run("invoice.invoice.create_from_sale", {"sale": sale.number})
    assert failed_ids() == ({voided.id}, 1)

    run("sale.sale.issue_documents", {"sale": sale.number})
    assert failed_ids() == (set(), 0)
    assert (state(completed), state(voided)) == (("pending", 0), ("pending", 0))
    relay_pass()
    assert Invoice.objects.filter(source_sale_id=sale.id).count() == 2


def test_a_refunds_failed_event_leaves_with_that_refunds_rectifying_invoice_and_a_discarded_one_stays(charge):
    sale = charge("failed-ev-0005")
    payment = Sale.objects.get(pk=sale.id).payments.get()
    for reason in ("Broken", "Wrong size", "Late"):
        run(
            "sale.sale.refund",
            {
                "sale_id": str(sale.id),
                "reason": reason,
                "allocations": [{"payment_id": str(payment.id), "amount": 100}],
                "lines": [],
            },
        )
    first, second, third = Refund.objects.filter(sale_id=sale.id).order_by("created_at", "id")
    given_up("sale.sale.completed", sale_id=str(sale.id))
    first_failed = given_up("sale.sale.refunded", refund_id=str(first.id))
    second_failed = given_up("sale.sale.refunded", refund_id=str(second.id))
    discarded = given_up("sale.sale.refunded", status=EventDelivery.Status.DISCARDED, refund_id=str(third.id))
    run("invoice.issuer.update", ISSUER)
    run("invoice.invoice.create_from_sale", {"sale": sale.number})

    run("invoice.invoice.rectify_from_refund", {"refund_id": str(first.id)})
    assert failed_ids() == ({second_failed.id}, 1)
    assert state(first_failed) == ("pending", 0)

    run("sale.sale.issue_documents", {"sale": sale.number})
    assert failed_ids() == (set(), 0)
    assert state(discarded) == (EventDelivery.Status.DISCARDED, relay.MAX_ATTEMPTS)

    # The relay hands every resent event over and each finds its document done: none is issued again.
    relay_pass()
    assert (state(first_failed), state(second_failed)) == (("delivered", 1), ("delivered", 1))
    assert (Invoice.objects.count(), Record.objects.count()) == (4, 4)


def test_another_business_failed_events_are_never_touched(charge, hub_b):
    sale = charge("failed-ev-0006")
    mine = given_up("sale.sale.completed", sale_id=str(sale.id))
    with use_hub(hub_b):
        event = OutboxEvent.objects.create(
            scope_kind=B.kind, scope_key=B.key, name="sale.sale.completed", payload={"sale_id": str(sale.id)}
        )
        theirs = EventDelivery.objects.create(
            event=event, app_label="invoice", status=DEAD, attempts=8, next_attempt_at=timezone.now()
        )
    run("invoice.issuer.update", ISSUER)

    run("sale.sale.issue_documents", {"sale": sale.number})

    assert state(mine) == ("pending", 0)
    with use_hub(hub_b):
        assert state(theirs) == (DEAD, 8)
