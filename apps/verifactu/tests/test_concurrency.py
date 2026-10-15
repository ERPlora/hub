"""Several devices at once (VERIFACTU-F13, F15, F20): real sessions in threads, real row locks.

Six emissions at once (Invoicing seals inside each) and six invoices sealed at once take six consecutive numbers of their chain, each chained to the one before, never
two with the same previous fingerprint; the same invoice delivered twice at once is one record; two passes of
the queue at once never send the same chain twice (``SKIP LOCKED`` on its send control).
"""

import threading
import time

import pytest
from django.db import connection

from apps.verifactu import gateway
from apps.verifactu.models import Record

from apps.verifactu.tests.conftest import A, answering, manual, run

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _committed(committed_factory_data):
    """Every test here starts from the committed factory data and the issuer (``conftest``)."""


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except Exception as error:  # reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def tickets(count: int):
    return [
        manual(
            [
                {
                    "description": "Cut",
                    "quantity": "1",
                    "unit_price": 1000 + n,
                    "tax_rate": "21",
                }
            ],
            series_code="TICKET",
        )
        for n in range(count)
    ]


def seal(invoice):
    return lambda: run("verifactu.record.create", {"invoice_id": str(invoice.id)})


def test_six_emissions_at_once_make_one_chain_without_holes():
    # Six devices issue at once: each emission seals its record in its own transaction (Invoicing asks by name).
    results = at_once(
        *(
            (lambda n=n: manual(
                [{"description": "Cut", "quantity": "1", "unit_price": 1000 + n, "tax_rate": "21"}],
                series_code="TICKET",
            ))
            for n in range(6)
        )
    )
    assert all(not isinstance(result, Exception) for result in results), results
    assert {result.verifactu_status for result in results} == {"sealed"}
    records = list(Record.objects.order_by("sequence"))
    assert [record.sequence for record in records] == [1, 2, 3, 4, 5, 6]
    assert sorted(record.invoice_id for record in records) == sorted(result.id for result in results)
    for previous, record in zip(records, records[1:]):
        assert record.previous_fingerprint == previous.fingerprint
    assert run("verifactu.chain.validate").valid is True


def test_six_invoices_sealed_at_once_make_one_chain_without_holes(invoice_does_not_seal):
    results = at_once(*(seal(invoice) for invoice in tickets(6)))
    assert all(not isinstance(result, Exception) for result in results), results
    records = list(Record.objects.order_by("sequence"))
    assert [record.sequence for record in records] == [1, 2, 3, 4, 5, 6]
    assert records[0].previous_fingerprint == ""
    for previous, record in zip(records, records[1:]):
        assert record.previous_fingerprint == previous.fingerprint
        assert record.previous_record_id == previous.id
    assert len({record.previous_fingerprint for record in records}) == 6
    assert run("verifactu.chain.validate").valid is True


def test_the_same_invoice_twice_at_once_is_one_record(invoice_does_not_seal):
    [invoice] = tickets(1)
    results = at_once(seal(invoice), seal(invoice))
    assert all(not isinstance(result, Exception) for result in results), results
    assert sorted(result.already for result in results) == [False, True]
    assert results[0].record.id == results[1].record.id
    assert Record.objects.count() == 1


def test_a_chain_held_too_long_leaves_the_document_pending_and_its_reaction_seals_it(monkeypatch):
    """A transient database error at the emission (another device holds the chain's lock past the lock timeout):
    Invoicing keeps the document «pending» and VeriFactu's reaction to its notice seals it once the lock is free."""
    from django.db import connection as default

    from apps.invoice import services as invoicing
    from apps.invoice.models import Invoice
    from apps.verifactu.models import Chain
    from apps.verifactu.tests.conftest import deliver

    tickets(1)  # the chain's head exists, committed
    real = invoicing.get_operation

    def busy_database(name):
        operation = real(name)
        if name != invoicing.VERIFACTU_RECORD:
            return operation

        def short_wait(ctx, data):
            with default.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '200ms'")
            return operation(ctx, data)

        short_wait.input = operation.input
        return short_wait

    monkeypatch.setattr(invoicing, "get_operation", busy_database)
    import psycopg

    other = psycopg.connect(**default.get_connection_params(), autocommit=False)  # another device, own session
    try:
        with other.cursor() as cursor:
            cursor.execute(f"SELECT 1 FROM {Chain._meta.db_table} FOR UPDATE")
            [invoice] = tickets(1)
        assert invoice.verifactu_status == "pending"
        assert Invoice.objects.filter(pk=invoice.id).exists()
        assert not Record.objects.filter(invoice_id=invoice.id).exists()
    finally:
        other.rollback()
        other.close()
    result = deliver("invoice.invoice.issued")
    assert (result.already, result.record.invoice_id, result.record.sequence) == (False, invoice.id, 2)
    assert Record.objects.get(invoice_id=invoice.id).created_by == "system"


def test_two_passes_at_once_never_send_the_same_chain_twice(settings, monkeypatch):
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    tickets(3)  # each emission seals its record
    calls = []
    accept = answering()

    def slow(path, payload):
        calls.append(path)
        time.sleep(0.5)  # holds the chain's send control while the other pass arrives
        return accept(payload)

    monkeypatch.setattr(gateway, "_reply", slow)
    process = lambda: run("verifactu.contingency.process")  # noqa: E731
    results = at_once(process, process)
    assert all(not isinstance(result, Exception) for result in results), results
    assert calls == [gateway.SUBMIT_PATH]
    assert sorted(result.sent for result in results) == [0, 3]
    assert set(Record.objects.values_list("status", flat=True)) == {"accepted"}
