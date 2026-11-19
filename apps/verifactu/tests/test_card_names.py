"""The card of a write of VeriFactu says which record it acts on by the number of its invoice, as the records' list and
the record's own page name it («Record TICKET-2026-000012»), and the invoice a record is sealed for by its number, as
Invoicing names it: read as whoever asks, never by its id. Whoever may not read them, or a record that is not there,
is told nothing about it; and saying it changes nothing of the record nor sends anything."""

import dataclasses
import socket

import pytest
from live.context import OperationContext, Scope
from live.models import OutboxEvent
from live.operations import get

from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import HUB_DB, ISSUER, A, B, ctx_for, run
from base import assistant
from base.tests.test_assistant_card_values_references import AN_ID

pytestmark = HUB_DB

A_MISSING_ID = "0192f0b2-3333-7000-8000-000000000003"

#: Each write of VeriFactu that takes a record by its id.
ON_A_RECORD = [
    "verifactu.contingency.retry",
    "verifactu.record.cancel",
    "verifactu.record.correct",
    "verifactu.record.reconcile",
    "verifactu.record.transmit",
]
#: What the card calls the record and the invoice, as the VeriFactu screens do.
TITLES = {"en": ("Record", "Invoice"), "es": ("Registro", "Factura")}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Nothing here may leave the machine: a connection opened from Python fails the test (the database's is not)."""

    def refuse(*args, **kwargs):
        raise AssertionError(f"a test of the card opened a connection: {args!r}")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def sealed(unit_price: int = 1000, scope: Scope = A) -> Record:
    """A ticket issued in the business of ``scope``, with its record sealed at the emission."""
    lines = [{"description": "Cut", "quantity": "1", "unit_price": unit_price, "tax_rate": "21"}]
    invoice = run("invoice.invoice.create", {"series_code": "TICKET", "lines": lines}, ctx_for(scope=scope))
    return Record.objects.get(invoice_id=invoice.id)


def fields_of(write: str, arguments: dict, language: str = "en", ctx: OperationContext | None = None) -> dict:
    card = assistant.cards.card(get(write), arguments, language, ctx or ctx_for(language=language))
    return {field["name"]: field for field in card["fields"]}


def shown(write: str, arguments: dict, ctx: OperationContext | None = None) -> dict:
    return {name: field["value"] for name, field in fields_of(write, arguments, ctx=ctx).items()}


def without(permission: str, scope: Scope = A) -> OperationContext:
    """An admin of ``scope`` without ``permission``: a combination no role has."""
    ctx = ctx_for(scope=scope)
    return dataclasses.replace(ctx, permissions=frozenset(ctx.permissions) - {permission})


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("write", ON_A_RECORD)
def test_a_write_says_the_record_it_takes_by_its_invoice_number(issuer, write, language):
    """The case of the issue, retrying a record of the queue: «Registro: TICKET-2026-000001», never its id."""
    record = sealed()
    field = fields_of(write, {"record_id": str(record.id)}, language)["record_id"]
    assert (field["label"], field["value"]) == (TITLES[language][0], record.invoice_number)


@pytest.mark.parametrize("language", ["en", "es"])
def test_sealing_an_invoice_says_the_invoice_by_its_number(issuer, language):
    record = sealed()
    field = fields_of("verifactu.record.create", {"invoice_id": str(record.invoice_id)}, language)["invoice_id"]
    assert (field["label"], field["value"]) == (TITLES[language][1], record.invoice_number)


def test_among_several_records_each_id_names_its_own(issuer):
    records = [sealed(1000), sealed(2000)]
    for listed in (records, list(reversed(records))):
        for write in ON_A_RECORD:
            said = [shown(write, {"record_id": str(record.id)})["record_id"] for record in listed]
            assert said == [record.invoice_number for record in listed], write


@pytest.mark.parametrize(
    ("write", "datum", "permission"),
    [(write, "record_id", "verifactu.view_record") for write in ON_A_RECORD]
    + [("verifactu.record.create", "invoice_id", "invoice.view_invoice")],
)
def test_whoever_may_not_read_it_is_told_nothing_of_it(issuer, write, datum, permission):
    record = sealed()
    arguments = {datum: str({"record_id": record.id, "invoice_id": record.invoice_id}[datum])}
    assert datum in shown(write, arguments)  # positive control
    said = shown(write, arguments, ctx=without(permission))
    assert datum not in said
    assert not AN_ID.search(str(said))


@pytest.mark.parametrize(("write", "datum"), [(write, "record_id") for write in ON_A_RECORD] + [
    ("verifactu.record.create", "invoice_id")
])
def test_what_is_not_there_is_left_out(issuer, write, datum):
    assert shown(write, {datum: A_MISSING_ID}) == {}


def test_nobody_behind_the_request_reads_no_record(issuer):
    """An automation's card (no person at hand) names no record: nothing is read for anybody."""
    record = sealed()
    card = assistant.cards.card(get("verifactu.record.cancel"), {"record_id": str(record.id), "reason": "Twice"}, "en")
    assert {field["name"]: field["value"] for field in card["fields"]} == {"reason": "Twice"}


def test_a_record_of_another_business_is_left_out(issuer, in_business_b):
    """Each business in its own database, as production: an id of A names nothing in B."""
    in_a = sealed()
    assert "record_id" in shown("verifactu.record.transmit", {"record_id": str(in_a.id)})  # positive control
    with in_business_b():
        run("invoice.issuer.update", ISSUER, ctx_for(scope=B))
        sealed(scope=B)
        for write in ON_A_RECORD:
            assert shown(write, {"record_id": str(in_a.id)}, ctx=ctx_for(scope=B)) == {}, write


def test_saying_the_record_changes_nothing_of_it_nor_sends_anything(issuer):
    """The card only reads: the record keeps its status, fingerprint, attempts and turn in the queue, and no event is
    written for anybody to send."""
    record = sealed()
    kept = ("status", "fingerprint", "attempts", "next_attempt_at", "transmitted_at", "updated_at")
    before = Record.objects.filter(pk=record.pk).values(*kept).get()
    events = OutboxEvent.objects.count()
    for write in ON_A_RECORD:
        assert "record_id" in shown(write, {"record_id": str(record.id)})
    assert shown("verifactu.record.create", {"invoice_id": str(record.invoice_id)})
    assert Record.objects.filter(pk=record.pk).values(*kept).get() == before
    assert OutboxEvent.objects.count() == events
