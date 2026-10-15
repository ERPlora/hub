"""The data of the verifactu app: what the database itself guarantees (one configuration row, one chain head
and one send control per issuer and environment, one sequence number per chain, one original alta per invoice
and environment, the statuses), and the texts each model shows."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.invoice.models import Invoice, InvoiceSeries
from apps.verifactu.models import (
    AeatRecord,
    Chain,
    Config,
    Event,
    Record,
    SendControl,
    backoff,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def invoice(db):
    series = InvoiceSeries.objects.create(
        code="TICKET", name="POS tickets", invoice_type="F2", year=2026, prefix="TICKET"
    )
    return Invoice.objects.create(
        invoice_type="F2",
        series=series,
        series_code="TICKET",
        year=2026,
        sequence=1,
        number="TICKET-2026-000001",
        issue_date=dt.date(2026, 10, 14),
        operation_date=dt.date(2026, 10, 14),
        issuer_name="Peluquería Ana SL",
        issuer_tax_id="B12345674",
        description="Venta 20261014-0001",
        base_amount=1000,
        tax_amount=210,
        total_amount=1210,
        tax_breakdown=[],
    )


def record(invoice, **more) -> Record:
    fields = {
        "record_type": Record.Type.ALTA,
        "environment": Config.Environment.TESTING,
        "issuer_nif": "B12345674",
        "issuer_name": "Peluquería Ana SL",
        "sequence": 1,
        "invoice": invoice,
        "invoice_number": invoice.number,
        "issue_date": invoice.issue_date,
        "invoice_type": "F2",
        "base_amount": 1000,
        "tax_amount": 210,
        "total_amount": 1210,
        "generated_at": "2026-10-14T10:00:00+02:00",
        "generated_on": timezone.now(),
        "fingerprint": "A" * 64,
        "qr_url": "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674",
    }
    fields.update(more)
    return Record.objects.create(**fields)


def test_there_is_one_configuration_row_and_it_starts_in_testing_through_erplora():
    config = Config.objects.create()
    assert config.environment == "testing"
    assert config.route == "erplora"
    assert config.multiple_taxpayers == ""
    assert config.representation_status == "none"
    with pytest.raises(IntegrityError), transaction.atomic():
        Config.objects.create()


def test_one_chain_head_and_one_send_control_per_issuer_and_environment():
    Chain.objects.create(issuer_nif="B12345674", environment="testing")
    Chain.objects.create(issuer_nif="B12345674", environment="production")
    SendControl.objects.create(issuer_nif="B12345674", environment="testing")
    with pytest.raises(IntegrityError), transaction.atomic():
        Chain.objects.create(issuer_nif="B12345674", environment="testing")
    with pytest.raises(IntegrityError), transaction.atomic():
        SendControl.objects.create(issuer_nif="B12345674", environment="testing")


def test_a_sequence_number_is_given_once_per_chain(invoice):
    record(invoice)
    record(invoice, environment="production")  # another chain
    with pytest.raises(IntegrityError), transaction.atomic():
        record(invoice, correction=True)  # same chain, same number


def test_one_original_alta_per_invoice_and_environment(invoice):
    record(invoice)
    with pytest.raises(IntegrityError), transaction.atomic():
        record(invoice, sequence=2)
    # A correction (subsanación) and an anulación of the same invoice are new records of the chain.
    record(invoice, sequence=2, correction=True)
    record(
        invoice,
        sequence=3,
        record_type=Record.Type.ANULACION,
        invoice_type="",
        base_amount=None,
        tax_amount=None,
        total_amount=None,
    )


def test_the_status_is_one_of_the_five(invoice):
    with pytest.raises(IntegrityError), transaction.atomic():
        record(invoice, status="error")


def test_an_alta_carries_its_amounts_and_an_anulacion_none(invoice):
    with pytest.raises(IntegrityError), transaction.atomic():
        record(invoice, total_amount=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        record(invoice, record_type=Record.Type.ANULACION, invoice_type="")


def test_a_fingerprint_is_64_characters(invoice):
    with pytest.raises(IntegrityError), transaction.atomic():
        record(invoice, fingerprint="ABC")


def test_a_record_reads_as_its_invoice_and_its_sequence(invoice):
    assert str(record(invoice)) == "TICKET-2026-000001 (#1, testing)"


def test_unsent_and_in_the_aeat():
    assert Record.UNSENT == ("pending", "sent")
    assert set(Record.IN_AEAT) == {"accepted", "accepted_with_errors"}


@pytest.mark.parametrize(
    ("attempts", "minutes"), [(1, 5), (2, 10), (3, 20), (4, 40), (5, 60), (9, 60)]
)
def test_the_wait_doubles_from_five_minutes_up_to_an_hour(attempts, minutes):
    assert backoff(attempts) == dt.timedelta(minutes=minutes)


def test_an_event_composes_its_message_in_the_readers_language():
    event = Event.objects.create(
        kind=Event.Kind.CHAIN_BROKEN,
        severity=Event.Severity.CRITICAL,
        message_key="chain_broken",
        params={"first_invalid_sequence": 7, "issuer_nif": "B12345674"},
    )
    from django.utils import translation

    with translation.override("en"):
        assert event.message() == "Fingerprint chain BROKEN at sequence 7 (B12345674)."
    with translation.override("es"):
        assert (
            event.message() == "Cadena de huellas ROTA en la secuencia 7 (B12345674)."
        )


def test_an_event_whose_key_is_unknown_still_reads():
    event = Event(
        kind=Event.Kind.CONFIG_CHANGED,
        severity=Event.Severity.INFO,
        message_key="nope",
        params={},
    )
    assert event.message() == "nope"


def test_an_aeat_snapshot_row_reads_as_its_invoice():
    row = AeatRecord.objects.create(
        issuer_nif="B12345674",
        environment="testing",
        invoice_number="T-1",
        fingerprint="A" * 64,
        state="Correcto",
    )
    assert str(row) == "T-1 (B12345674)"
