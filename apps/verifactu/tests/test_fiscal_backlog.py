"""Since when VeriFactu's oldest record waits to reach the AEAT (hub#488; VERIFACTU-F20; PLAN-AWS §8).

The platform's metrics (``base.metrics``) ask every app's ``fiscal_pending_since`` in each database they read and
publish the age of the oldest answer as ``ERPlora/Fiscal`` ``OldestPendingAgeSeconds``, which pages the team after
5 minutes. The queue is the records themselves: one not in the AEAT yet (``Record.UNSENT``: pending, a retry waiting
included, or sent without an answer) waits since it was created. Only production counts: a record of the AEAT's test
environment files nothing (a demo, a business trying VeriFactu out), so its wait never pages anyone. What the AEAT
answered (accepted, with errors, rejected) has left the queue.
"""

import datetime as dt
from itertools import count

import pytest
from django.apps import apps
from django.utils import timezone

from apps.invoice.models import Invoice, InvoiceSeries
from apps.verifactu import queries
from apps.verifactu.models import Environment, Record

pytestmark = pytest.mark.django_db

_numbers = count(1)


def record(status: str, created: dt.datetime, environment: str = Environment.PRODUCTION) -> Record:
    """A record of its own invoice, in ``status`` and ``environment``, created at ``created``."""
    number = next(_numbers)
    series, _ = InvoiceSeries.objects.get_or_create(
        code="TICKET", year=2026, defaults={"name": "POS tickets", "invoice_type": "F2", "prefix": "TICKET"}
    )
    invoice = Invoice.objects.create(
        invoice_type="F2",
        series=series,
        series_code="TICKET",
        year=2026,
        sequence=number,
        number=f"TICKET-2026-{number:06d}",
        issue_date=dt.date(2026, 10, 14),
        operation_date=dt.date(2026, 10, 14),
        issuer_name="Peluquería Ana SL",
        issuer_tax_id="B12345674",
        description=f"Venta {number}",
        base_amount=1000,
        tax_amount=210,
        total_amount=1210,
        tax_breakdown=[],
    )
    return Record.objects.create(
        record_type=Record.Type.ALTA,
        environment=environment,
        issuer_nif="B12345674",
        issuer_name="Peluquería Ana SL",
        sequence=number,
        invoice=invoice,
        invoice_number=invoice.number,
        issue_date=invoice.issue_date,
        invoice_type="F2",
        base_amount=1000,
        tax_amount=210,
        total_amount=1210,
        generated_at="2026-10-14T10:00:00+02:00",
        generated_on=created,
        fingerprint="A" * 64,
        qr_url="https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674",
        status=status,
        created_at=created,
    )


def test_with_no_record_nothing_waits():
    assert queries.oldest_unsent_at() is None


@pytest.mark.parametrize("status", Record.UNSENT)
def test_a_production_record_not_in_the_aeat_yet_waits_since_it_was_created(status):
    created = timezone.now() - dt.timedelta(minutes=9)
    record(status, created)

    assert queries.oldest_unsent_at() == created


def test_the_oldest_of_the_records_still_to_send_is_the_one_read():
    now = timezone.now()
    record(Record.Status.PENDING, now - dt.timedelta(minutes=1))
    record(Record.Status.SENT, now - dt.timedelta(minutes=30))
    record(Record.Status.PENDING, now - dt.timedelta(minutes=6))

    assert queries.oldest_unsent_at() == now - dt.timedelta(minutes=30)


@pytest.mark.parametrize("status", sorted(set(Record.Status.values) - set(Record.UNSENT)))
def test_a_record_the_aeat_answered_has_left_the_queue(status):
    record(status, timezone.now() - dt.timedelta(days=2))

    assert queries.oldest_unsent_at() is None


def test_a_record_of_the_aeats_test_environment_never_counts():
    now = timezone.now()
    record(Record.Status.PENDING, now - dt.timedelta(hours=5), environment=Environment.TESTING)
    record(Record.Status.PENDING, now - dt.timedelta(minutes=2))

    assert queries.oldest_unsent_at() == now - dt.timedelta(minutes=2)


def test_the_app_answers_the_platforms_question_with_its_queue():
    created = timezone.now() - dt.timedelta(minutes=11)
    record(Record.Status.PENDING, created)

    assert apps.get_app_config("verifactu").fiscal_pending_since() == created
