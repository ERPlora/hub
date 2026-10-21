"""VeriFactu hears Invoicing through the worker's outbox relay, end to end (VERIFACTU-F13, F14).

Invoicing asks VeriFactu by name inside its own emission; when that could not seal (here VeriFactu is not found by
the emission), the invoice is issued with its notice ``invoice.invoice.issued`` in the outbox, and one tick of the
worker's real loop (``base.worker.run`` → ``base.relay``) hands it to VeriFactu, which seals its registration record
— once: a second tick, or an invoice already sealed at its emission, adds nothing. Pattern of
``apps/task/tests/test_relay.py`` (TASK-F15).
"""

import threading

import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.models import OutboxEvent

from apps.verifactu.models import Chain, Record
from apps.verifactu.tests.conftest import manual
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

pytestmark = pytest.mark.django_db

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


@pytest.fixture
def tick(db, monkeypatch, settings):
    """One tick of the worker's real loop, without the SaaS (``register_apps``) nor a gateway (nothing is presented),
    and, inside the test's transaction, without releasing the connections (that would close the test's own)."""
    settings.VERIFACTU_GATEWAY_URL = ""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def one_tick() -> None:
        stop = threading.Event()

        def wait(_seconds: float) -> bool:
            stop.set()
            return True

        now = timezone.now()
        assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now) == 0

    return one_tick


def delivery_to_verifactu(invoice_id) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of ``invoice_id``'s notice to VeriFactu."""
    event = OutboxEvent.objects.get(name="invoice.invoice.issued", payload__invoice_id=str(invoice_id))
    row = EventDelivery.objects.get(event_id=event.id, app_label="verifactu")
    return row.status, row.attempts


def test_an_invoice_issued_without_its_record_is_sealed_by_the_relay_once(issuer, invoice_does_not_seal, tick):
    invoice = manual(series_code="TICKET")
    assert invoice.verifactu_status == "unavailable"
    assert not Record.objects.exists()

    tick()

    record = Record.objects.get(invoice_id=invoice.id)
    assert (record.record_type, record.status, record.sequence) == ("alta", "pending", 1)
    assert delivery_to_verifactu(invoice.id)[0] == "delivered"
    tick()
    assert Record.objects.count() == 1
    assert Chain.objects.get().sequence == 1


def test_the_notice_of_an_invoice_sealed_at_its_emission_adds_nothing_through_the_relay(issuer, tick):
    invoice = manual(series_code="TICKET")
    sealed = Record.objects.get(invoice_id=invoice.id)

    tick()

    assert delivery_to_verifactu(invoice.id)[0] == "delivered"
    assert list(Record.objects.values_list("id", flat=True)) == [sealed.id]
    assert Chain.objects.get().sequence == 1
