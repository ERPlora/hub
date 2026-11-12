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
    OwnCertificate,
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
    assert not hasattr(config, "multiple_taxpayers")
    assert config.representation_status == "none"
    with pytest.raises(IntegrityError), transaction.atomic():
        Config.objects.create()


def test_own_certificate_is_a_single_row_without_the_blob_in_str():
    row = OwnCertificate.objects.create(
        holder="ACME SL",
        holder_tax_id="B12345674",
        kind="representative",
        expires_at=timezone.now() + dt.timedelta(days=30),
        sealed_blob=b"x-sealed-material",
        uploaded_by="u",
    )
    assert "sealed-material" not in str(row)
    assert "sealed-material" not in repr(row)
    assert "B12345674" in str(row)
    with pytest.raises(IntegrityError), transaction.atomic():
        OwnCertificate.objects.create(
            holder="B",
            holder_tax_id="B1",
            kind="personal",
            expires_at=timezone.now(),
            sealed_blob=b"y",
            uploaded_by="u",
        )


def test_the_configuration_no_longer_keeps_the_certificates_state():
    names = {field.name for field in Config._meta.get_fields()}
    assert not {name for name in names if name.startswith("own_certificate")}


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


NIF = {"issuer_nif": "B12345674"}
WHY = {"reason": "unreachable", "detail": "", "at": ""}
ACCEPTED = {"environment": "testing", "csv": "A-86MZ448LPLEBV7"}
RECOVERED = {**NIF, "invoice_number": "T-0007"}


@pytest.mark.parametrize(
    ("key", "params", "language", "said"),
    [
        ("deferred", {"count": 1, **WHY}, "en", "Not sent to the AEAT yet (1 record): "),
        ("deferred", {"count": 2, **WHY}, "en", "Not sent to the AEAT yet (2 records): "),
        ("deferred", {"count": 1, **WHY}, "es", "Aún no se ha enviado a la AEAT (1 registro): "),
        ("deferred", {"count": 2, **WHY}, "es", "Aún no se han enviado a la AEAT (2 registros): "),
        ("accepted", {"count": 1, **ACCEPTED}, "en", "AEAT (Testing (AEAT test)): 1 record accepted, CSV A-86MZ448LPLEBV7."),
        ("accepted", {"count": 2, **ACCEPTED}, "en", "AEAT (Testing (AEAT test)): 2 records accepted, CSV A-86MZ448LPLEBV7."),
        ("accepted", {"count": 1, **ACCEPTED}, "es", "AEAT (Pruebas (AEAT de pruebas)): 1 registro aceptado, CSV A-86MZ448LPLEBV7."),
        ("accepted", {"count": 2, **ACCEPTED}, "es", "AEAT (Pruebas (AEAT de pruebas)): 2 registros aceptados, CSV A-86MZ448LPLEBV7."),
        (
            "chain_valid",
            {"total": 1, **NIF},
            "en",
            "Fingerprint chain intact: 1 record with its SHA-256 chaining verified (B12345674). Amounts are not re-audited.",
        ),
        (
            "chain_valid",
            {"total": 2, **NIF},
            "en",
            "Fingerprint chain intact: 2 records with their SHA-256 chaining verified (B12345674). Amounts are not "
            "re-audited.",
        ),
        (
            "chain_valid",
            {"total": 1, **NIF},
            "es",
            "Cadena de huellas íntegra: 1 registro con su encadenado SHA-256 verificado (B12345674). No se re-auditan los "
            "importes.",
        ),
        (
            "chain_valid",
            {"total": 2, **NIF},
            "es",
            "Cadena de huellas íntegra: 2 registros con su encadenado SHA-256 verificado (B12345674). No se re-auditan "
            "los importes.",
        ),
        ("aeat_queried", {"count": 1, **NIF}, "en", "AEAT query: 1 record retrieved for B12345674."),
        ("aeat_queried", {"count": 2, **NIF}, "en", "AEAT query: 2 records retrieved for B12345674."),
        ("aeat_queried", {"count": 1, **NIF}, "es", "Consulta a la AEAT: 1 registro recuperado para B12345674."),
        ("aeat_queried", {"count": 2, **NIF}, "es", "Consulta a la AEAT: 2 registros recuperados para B12345674."),
        (
            "chain_recovered_from_aeat",
            {"found": 1, **RECOVERED},
            "en",
            "Chain recovered from the AEAT for B12345674: it continues after invoice T-0007 (1 record found).",
        ),
        (
            "chain_recovered_from_aeat",
            {"found": 2, **RECOVERED},
            "en",
            "Chain recovered from the AEAT for B12345674: it continues after invoice T-0007 (2 records found).",
        ),
        (
            "chain_recovered_from_aeat",
            {"found": 1, **RECOVERED},
            "es",
            "Cadena recuperada desde la AEAT para B12345674: continúa tras la factura T-0007 (1 registro encontrado).",
        ),
        (
            "chain_recovered_from_aeat",
            {"found": 2, **RECOVERED},
            "es",
            "Cadena recuperada desde la AEAT para B12345674: continúa tras la factura T-0007 (2 registros encontrados).",
        ),
    ],
)
def test_an_event_says_one_record_in_the_singular_and_several_in_the_plural(key, params, language, said):
    # hub#1275: the audit trail said «record(s)» whatever the number; the sentence is composed when it is read, so the
    # events already kept say it right too.
    from django.utils import translation

    event = Event(kind=Event.Kind.QUEUE_PROCESSED, message_key=key, params=params)
    with translation.override(language):
        assert event.message().startswith(said)


def test_an_event_whose_count_is_missing_still_reads():
    # The number picks the singular or the plural: without it the sentence cannot be chosen, and it reads as its key,
    # as an unknown one does, never as an empty line.
    event = Event(kind=Event.Kind.ACCEPTED, message_key="accepted", params={"csv": "X"})
    assert event.message() == "accepted"


def test_an_aeat_snapshot_row_reads_as_its_invoice():
    row = AeatRecord.objects.create(
        issuer_nif="B12345674",
        environment="testing",
        invoice_number="T-1",
        fingerprint="A" * 64,
        state="Correcto",
    )
    assert str(row) == "T-1 (B12345674)"
