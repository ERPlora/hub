"""The fingerprint of a record: sealing writes it and chain validation recomputes it with the same function.

The vectors are the AEAT's published cases (the same ones ``test_chain.py`` checks on the bare hash) and an alta
and its anulación sealed end to end at a fixed instant, whose fingerprints are pinned: a change to how a record's
fields reach the hash breaks them.
"""

import datetime as dt

from django.utils import timezone

from apps.verifactu.models import Record
from apps.verifactu.services import chains, sealing
from apps.verifactu.tests.conftest import HUB_DB, run, ticket
from apps.verifactu.tests.test_chain import CASE_1, CASE_2, CASE_3

SEALED_AT = dt.datetime(2026, 6, 10, 10, 34, 56, tzinfo=dt.UTC)
SEALED_ALTA = "1217CADC785FE24C98EF26C950909C1690E47CF4F48B26C3FCE7854EBC0B337B"
SEALED_ANULACION = "3C496F73CBFACB3A2552EA39106CD41F37E4721B480D8DB35AADD19843CD1AA6"


def official(record_type: str, number: str, previous: str, generated_at: str) -> Record:
    """A record with the fields of one of the AEAT's published cases (an F1 of 123.45 € with 12.35 € of tax)."""
    return Record(
        record_type=record_type,
        issuer_nif="89890001K",
        invoice_number=number,
        issue_date=dt.date(2024, 1, 1),
        invoice_type="F1",
        tax_amount=1235,
        total_amount=12345,
        previous_fingerprint=previous,
        generated_at=generated_at,
    )


def test_the_aeat_cases_give_their_published_fingerprints():
    cases = [
        official(Record.Type.ALTA, "12345678/G33", "", "2024-01-01T19:20:30+01:00"),
        official(Record.Type.ALTA, "12345679/G34", CASE_1, "2024-01-01T19:20:35+01:00"),
        official(Record.Type.ANULACION, "12345679/G34", CASE_2, "2024-01-01T19:20:40+01:00"),
    ]
    assert [sealing._fingerprint_of(record) for record in cases] == [CASE_1, CASE_2, CASE_3]


def test_chain_validation_recomputes_with_the_function_sealing_writes_with():
    assert chains._fingerprint_of is sealing._fingerprint_of


@HUB_DB
def test_an_alta_and_its_anulacion_sealed_end_to_end_keep_their_fingerprints(issuer, monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: SEALED_AT)
    alta = Record.objects.get(invoice_id=ticket().id)
    result = run("verifactu.record.cancel", {"invoice_number": alta.invoice_number, "reason": "Duplicated ticket"})
    anulacion = Record.objects.get(pk=result.record.id)
    assert (alta.generated_at, alta.invoice_number, alta.tax_amount, alta.total_amount) == (
        "2026-06-10T12:34:56+02:00",
        "TICKET-2026-000001",
        210,
        1210,
    )
    assert (alta.fingerprint, anulacion.previous_fingerprint) == (SEALED_ALTA, SEALED_ALTA)
    assert anulacion.fingerprint == SEALED_ANULACION
    assert run("verifactu.chain.validate").valid is True
