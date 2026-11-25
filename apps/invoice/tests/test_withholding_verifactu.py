"""What VeriFactu declares of an invoice with an IRPF withholding: the record of the same invoice without it, to the last
character. The tax agency says the withholding is no part of the record nor of its ImporteTotal. The records are sealed in
VeriFactu's testing environment and never sent: nothing here leaves the machine."""

import contextlib
import re

import pytest
from live.operations import atomic

from apps.invoice.models import Invoice
from apps.invoice.tests.conftest import HUB_DB, run
from apps.invoice.tests.manual import HUNDRED, NOON, line, manual, withheld
from apps.verifactu.models import Record

pytestmark = [HUB_DB, pytest.mark.usefixtures("issuer", "nothing_leaves")]


def record_of(answer) -> dict:
    """Everything VeriFactu keeps and prints of a document: its record's columns, its XML, its fingerprint and its QR.
    Only the ids of the rows are left out, new in each one; the chain is in the previous record's number and fingerprint."""
    record = Record.objects.get(invoice_id=answer.id)
    kept = {
        field.attname: getattr(record, field.attname)
        for field in Record._meta.concrete_fields
        if field.attname not in ("id", "invoice_id", "previous_record_id")
    }
    qr = run("verifactu.record.by_invoice", {"invoice_id": str(answer.id)}).record
    return {**kept, "qr_url": qr.qr_url, "qr_svg": qr.qr_svg}


class Undo(Exception):
    """Takes back what a block issued."""


def undone(issue) -> dict:
    """The record of what ``issue()`` issues, taken back afterwards: the next document gets the same number, the same
    place in the chain and the same clock."""
    record: dict = {}
    with contextlib.suppress(Undo), atomic():
        record = record_of(issue())
        raise Undo
    assert not Record.objects.exists()
    return record


def test_the_record_of_an_invoice_is_the_same_with_it_and_without_it(at):
    at(NOON)
    plain = undone(lambda: manual(lines=[HUNDRED, line(3333, "10")]))
    assert not Invoice.objects.exists()
    carried = undone(lambda: withheld(15, HUNDRED, line(3333, "10")))
    assert carried == plain
    # What is compared is the record in full: the amount, the chain and the QR are in it.
    assert plain["total_amount"] == 15766
    assert re.findall(r"<sum1:ImporteTotal>([^<]+)<", plain["xml"]) == ["157.66"]
    assert len(plain["fingerprint"]) == 64
    assert "importe=157.66" in plain["qr_url"]


def test_the_record_of_its_rectification_is_the_same_too(at):
    at(NOON)

    def rectified(**more):
        original = manual(lines=[HUNDRED], **more)
        return run("invoice.invoice.rectify", {"number": original.number, "reason": "Wrong price"}).invoice

    plain = undone(rectified)
    assert undone(lambda: rectified(withholding_rate=15)) == plain
    assert (plain["total_amount"], plain["previous_number"]) == (-12100, "FACT-2026-000001")
    assert len(plain["previous_fingerprint"]) == 64
