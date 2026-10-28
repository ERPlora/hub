"""VeriFactu is only for businesses in Spain (VERIFACTU-F01, F13; FIX-HUB-VERIFACTU-ON-FOR-A-BUSINESS-OUTSIDE-SPAIN).

RD 1007/2023 and Orden HAC/1177/2024 bind the taxpayers of Spain (the Canary Islands, Ceuta and Melilla included: a
region of ES, not another country). A business erplora.com registered in another country (``base.Hub.country``, as
``PUT /internal/hubs/{id}`` writes it) files nothing with the AEAT, so with VeriFactu on it behaves as if it were off:

- its invoices are issued without a record («unavailable»), never undone by a refusal of VeriFactu, and the reaction
  to ``invoice.invoice.issued`` seals nothing;
- nothing that seals or reaches the AEAT runs (404 ``app_inactive``, with the reason);
- the queue sends nothing, and what was sealed before stays (fiscal records are never deleted) with the reason it
  does not leave; the invoice shows no VeriFactu receipt, and the veto to turn the app off does not trap it.

A business without a country (a demo) is in ERPlora's market, Spain: it files as before.
"""

import base64

import pytest
from live.context import OperationContext, Scope, system_context
from live.errors import AppInactive
from live.operations import get

from apps.invoice.models import Invoice
from apps.verifactu import queries
from apps.verifactu.models import Record
from apps.verifactu.tests.conftest import A, B, ISSUER, RECIPIENT, ctx_for, deliver, manual, run
from base import activation
from base.models import Hub

pytestmark = pytest.mark.django_db

ONLY_IN_SPAIN = "VeriFactu is only for businesses in Spain."
NOT_SENT = "this business is not in Spain: VeriFactu is only for businesses in Spain, so nothing is sent to the AEAT"
CUT = [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}]
PLATFORM = Scope("host", "erplora")


def business_in(country: str, slug: str = "a") -> None:
    """The country erplora.com registered for the business of ``slug`` (``PUT /internal/hubs/{id}``)."""
    Hub.objects.filter(slug=slug).update(country=country)


def ticket(ctx=None):
    return run("invoice.invoice.create", {"series_code": "TICKET", "lines": CUT}, ctx)


def sealed_in_spain() -> Record:
    """A ticket issued while the business was in Spain: its record sealed and waiting («pending»)."""
    business_in("ES")
    record = Record.objects.get(invoice_id=ticket().id)
    assert record.status == Record.Status.PENDING
    return record


# (a) Issuing outside Spain


def test_an_invoice_of_a_business_in_poland_is_issued_without_a_record(issuer):
    business_in("PL")
    invoice = manual(**RECIPIENT)
    assert invoice.verifactu_status == "unavailable"
    assert Invoice.objects.filter(pk=invoice.id, number=invoice.number).exists()
    assert not Record.objects.exists()


def test_what_verifactu_would_refuse_in_spain_never_undoes_an_invoice_in_poland(issuer, at_emission):
    # In Spain VeriFactu refuses this F1 at its emission (its customer's tax ID is gone: verifactu.recipient_required),
    # which undoes the whole emission (test_integration_invoice); in Poland it seals nothing, so the invoice is issued.
    at_emission(lambda row: {"customer_tax_id": ""})
    business_in("PL")
    invoice = manual(**RECIPIENT)
    assert invoice.verifactu_status == "unavailable"
    assert Invoice.objects.filter(pk=invoice.id).exists()
    assert not Record.objects.exists()


def test_the_reaction_to_an_issued_invoice_seals_nothing_outside_spain(issuer, invoice_does_not_seal):
    business_in("PL")
    ticket()
    assert deliver("invoice.invoice.issued") is None
    assert not Record.objects.exists()


# (b) Spain as today


@pytest.mark.parametrize("country", ["ES", ""])
def test_a_business_in_spain_or_without_a_country_still_seals_its_record(issuer, country):
    business_in(country)
    invoice = ticket()
    assert invoice.verifactu_status == "sealed"
    assert Record.objects.get(invoice_id=invoice.id).status == Record.Status.PENDING


def test_each_hub_reads_its_own_business_s_country(issuer):
    business_in("PL", "a")
    business_in("ES", "b")
    run("invoice.issuer.update", ISSUER, ctx_for(scope=B))
    in_poland, in_spain = ticket(), ticket(ctx_for(scope=B))
    assert (in_poland.verifactu_status, in_spain.verifactu_status) == ("unavailable", "sealed")
    assert list(Record.objects.values_list("invoice_id", flat=True)) == [in_spain.id]


def test_erploras_own_hub_reads_its_country_from_the_platform_too(db, settings, monkeypatch):
    # FIX-HUB-VERIFACTU-OWN-SHORTCUT-FOR-PLATFORM-HUB-COUNTRY: ``base.business.get`` answers ERPlora's own hub (hub#329),
    # so VeriFactu asks it there as anywhere else, never a second source of the same country that drifts in silence if
    # the platform moves where its hub's country comes from (here, an answer other than ``PLATFORM_ISSUER_COUNTRY``).
    settings.PLATFORM_HUB_SLUG = PLATFORM.key
    settings.PLATFORM_ISSUER_COUNTRY = "ES"
    assert not queries.outside_spain(PLATFORM)

    business = get(queries.BUSINESS)
    answer = business.fn
    monkeypatch.setattr(business, "fn", lambda ctx, data: {**answer(ctx, data), "country": "PL"})

    assert queries.business_country(PLATFORM) == "PL"
    assert queries.outside_spain(PLATFORM)


# (c) The queue


def test_the_queue_sends_nothing_of_a_business_outside_spain(issuer, gateway_answers):
    record = sealed_in_spain()
    business_in("PL")

    for ctx in (ctx_for(), system_context(A)):
        sent = run("verifactu.contingency.process", {}, ctx)
        assert (sent.sent, sent.waiting, sent.reason, sent.message) == (0, 1, "outside_spain", NOT_SENT)
    assert gateway_answers.calls == []
    kept = Record.objects.get(pk=record.pk)
    assert (kept.status, kept.wait_reason) == (Record.Status.PENDING, "outside_spain")


def test_a_record_left_unsent_outside_spain_says_why_and_offers_nothing_to_do(issuer):
    record = sealed_in_spain()
    business_in("PL")
    shown = run("verifactu.record.get", {"record_id": str(record.id)})
    assert [(reason.code, reason.message) for reason in shown.waiting] == [("outside_spain", NOT_SENT)]
    # It never goes out: no next attempt, and nothing to send, correct or cancel.
    assert (shown.next_attempt_at, shown.can_transmit, shown.can_correct, shown.can_cancel) == (None, False, False, False)
    config = run("verifactu.config.get")
    assert [reason.code for reason in config.reasons] == ["outside_spain"]
    # What keeps it from going live is that alone: nothing else would let it.
    assert [reason.code for reason in config.live_blockers] == ["outside_spain"]


def test_a_rejected_record_outside_spain_offers_no_correction(issuer):
    record = sealed_in_spain()
    Record.objects.filter(pk=record.pk).update(status=Record.Status.REJECTED)
    assert run("verifactu.record.get", {"record_id": str(record.id)}).can_correct is True
    business_in("PL")
    assert run("verifactu.record.get", {"record_id": str(record.id)}).can_correct is False


# (d) What seals or reaches the AEAT, the receipt and the veto


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("verifactu.record.create", "record"),
        ("verifactu.record.correct", "record"),
        ("verifactu.record.cancel", "record"),
        ("verifactu.record.transmit", "record"),
        ("verifactu.record.reconcile", "record"),
        ("verifactu.aeat.query", {}),
        ("verifactu.chain.recover_from_aeat", {}),
        ("verifactu.diagnostic.run", {}),
        ("verifactu.test_invoice.create", {}),
        ("verifactu.config.go_live", {}),
        ("verifactu.representation.submit", "authorisation"),
    ],
)
def test_nothing_seals_nor_reaches_the_aeat_outside_spain(issuer, gateway_answers, name, data):
    record = sealed_in_spain()
    business_in("PL")
    if data == "authorisation":
        signed = base64.b64encode(b"%PDF-1.7 signed").decode()
        data = {"signer_document_type": "dni", "signed_model_base64": signed, "id_copy_base64": signed}
    if data == "record":
        data = {"record_id": str(record.id)}
        if name == "verifactu.record.create":
            data = {"invoice_id": str(record.invoice_id)}
        if name == "verifactu.record.cancel":
            data["reason"] = "Issued by error"
    invoices = Invoice.objects.count()

    with pytest.raises(AppInactive) as refused:
        run(name, data)

    assert (refused.value.code, refused.value.message) == ("app_inactive", ONLY_IN_SPAIN)
    assert list(Record.objects.values_list("pk", flat=True)) == [record.pk]
    assert Invoice.objects.count() == invoices
    assert gateway_answers.calls == []


def test_the_refusal_is_said_in_spanish(issuer):
    business_in("PL")
    with pytest.raises(AppInactive) as refused:
        run("verifactu.test_invoice.create", {}, ctx_for(language="es"))
    assert refused.value.message == "VeriFactu solo es para negocios de España."


def test_an_invoice_outside_spain_shows_no_verifactu_receipt(issuer):
    record = sealed_in_spain()
    assert run("verifactu.record.by_invoice", {"invoice_id": str(record.invoice_id)}).record is not None
    business_in("PL")
    assert run("verifactu.record.by_invoice", {"invoice_id": str(record.invoice_id)}).record is None


def test_records_that_will_never_be_sent_do_not_keep_verifactu_on_outside_spain(issuer):
    # In Spain a record still to send vetoes turning it off (VERIFACTU-F32); outside Spain it is never sent, so turning
    # VeriFactu off stops nothing: it goes off, and the record is kept as it is.
    record = sealed_in_spain()
    assert queries.disable_refusal(ctx_for()) is not None
    business_in("PL")
    turn_off = get("base.app.disable")
    administrator = OperationContext(scope=A, actor="ana", permissions=frozenset({"*"}))
    turn_off(administrator, turn_off.input.model_validate({"app": "verifactu"}))
    assert not activation.states_of(A)["verifactu"].on
    assert Record.objects.get(pk=record.pk).status == Record.Status.PENDING
