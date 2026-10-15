"""The events of the verifactu app and its one reaction: Invoicing's ``invoice.invoice.issued``, delivered from the
outbox. It is the backup: Invoicing asks by name inside its own emission (sealed by the issuer); the reaction,
run as the system, seals only what that emission could not (``invoice_does_not_seal``)."""

import pytest
from live.models import OutboxEvent

from apps.verifactu import events
from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import A, deliver, manual

pytestmark = pytest.mark.django_db


def test_the_events_it_records_are_named_app_entity_fact():
    assert events.ALL == [
        "verifactu.record.created",
        "verifactu.record.transmitted",
        "verifactu.record.rejected",
        "verifactu.record.accepted_with_errors",
        "verifactu.contingency.processed",
        "verifactu.contingency.retried",
        "verifactu.chain.validated",
        "verifactu.chain.recovered",
        "verifactu.aeat.queried",
        "verifactu.diagnostic.run",
        "verifactu.config.changed",
    ]


def test_it_reacts_to_an_issued_invoice_and_to_nothing_else():
    assert events.REACTIONS == {"invoice.invoice.issued": "verifactu.record.create"}


def test_a_real_issued_notice_seals_the_invoices_record_as_the_system(issuer, invoice_does_not_seal):
    invoice = manual(series_code="TICKET")
    notice = OutboxEvent.objects.get(name="invoice.invoice.issued")
    assert notice.payload["invoice_id"] == str(invoice.id)
    result = deliver("invoice.invoice.issued")
    record = Record.objects.get(pk=result.record.id)
    assert (record.invoice_id, record.created_by) == (invoice.id, "system")


def test_the_same_notice_twice_is_one_record(issuer, invoice_does_not_seal):
    manual(series_code="TICKET")
    first = deliver("invoice.invoice.issued")
    again = deliver("invoice.invoice.issued")
    assert (again.already, again.record.id) == (True, first.record.id)
    assert Record.objects.count() == 1


def test_a_notice_it_does_not_listen_to_is_ignored(issuer):
    assert events.react(A, "invoice.invoice.paid", {"invoice_id": "x"}) is None
