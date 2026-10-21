"""A charge that could not be invoiced is retried by the hub on its own (INVOICE-F06), through the worker's
real outbox relay (``base.relay``): the till charges without an issuer, the relay hands ``sale.sale.completed``
to Invoicing, which refuses and waits 2, 4, 8… s; once the issuer is set up, the next attempt issues the ticket
and Sales has its number in that same transaction. After the last attempt the delivery is given up and the
sale keeps waiting, in sight, for «Issue now».
"""

import datetime as dt
import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent

from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import ISSUER, run
from apps.sale.models import Sale
from apps.verifactu.models import Record
from base import catalog, relay, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

pytestmark = pytest.mark.django_db

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


@pytest.fixture
def tick(monkeypatch):
    """One tick of the worker's real loop at ``at``, without the SaaS (``register_apps``) and, inside the
    test's transaction, without releasing the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def once(at: dt.datetime) -> None:
        stop = threading.Event()

        def wait(_seconds: float) -> bool:
            stop.set()
            return True

        assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: at) == 0

    return once


def to_invoicing(sale) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the sale's ``sale.sale.completed`` to Invoicing."""
    event = OutboxEvent.objects.get(name="sale.sale.completed", payload__sale_id=str(sale.id))
    delivery = EventDelivery.objects.get(event_id=event.id, app_label="invoice")
    return delivery.status, delivery.attempts


def document_of(sale) -> tuple[str, str]:
    found = Sale.objects.get(pk=sale.id)
    return found.invoice_status, found.invoice_number


def test_a_charge_without_an_issuer_is_invoiced_by_the_relay_once_the_issuer_is_set_up(tick, product, charge):
    product("Shampoo", "SHA", 1210, "product.generic")
    sale = charge("relay-0001")
    now = timezone.now()
    tick(now)
    assert to_invoicing(sale) == ("pending", 1)
    assert document_of(sale) == ("pending", "")
    assert Invoice.objects.count() == 0

    run("invoice.issuer.update", ISSUER)
    # Before its wait is over nothing is tried again.
    tick(now + relay.backoff(1) - dt.timedelta(seconds=1))
    assert to_invoicing(sale) == ("pending", 1)
    tick(now + relay.backoff(1))
    assert to_invoicing(sale)[0] == "delivered"
    ticket = Invoice.objects.get(source_sale_id=sale.id)
    assert (ticket.invoice_type, ticket.status) == ("F2", "paid")
    assert document_of(sale) == ("issued", ticket.number)
    assert Record.objects.filter(invoice_id=ticket.id).count() == 1

    # Another tick, later, changes nothing: one ticket, one number, one «invoiced».
    tick(now + dt.timedelta(hours=2))
    assert Invoice.objects.filter(source_sale_id=sale.id).count() == 1
    assert OutboxEvent.objects.filter(name="sale.sale.invoiced", payload__sale_id=str(sale.id)).count() == 1


def test_after_the_last_attempt_the_sale_waits_for_issue_now(tick, product, charge):
    product("Shampoo", "SHA", 1210, "product.generic")
    sale = charge("relay-0002")
    at = timezone.now()
    for attempt in range(1, relay.MAX_ATTEMPTS + 1):
        tick(at)
        at += relay.backoff(attempt)
    assert to_invoicing(sale) == ("dead", relay.MAX_ATTEMPTS)
    assert document_of(sale) == ("pending", "")

    run("invoice.issuer.update", ISSUER)
    tick(at + dt.timedelta(hours=2))
    assert document_of(sale) == ("pending", "")
    issued = run("sale.sale.issue_documents", {"sale": sale.number})
    ticket = Invoice.objects.get(source_sale_id=sale.id)
    assert (issued.invoice_status, issued.invoice_number) == ("issued", ticket.number)
