"""The writes of the verifactu app (VERIFACTU-F04, F08–F11, F13–F15, F20–F30), with Invoicing's real documents.

Cases from the current module's tests (``arithmetic_integrity``, ``recipient_snapshot``, ``rectification_block``,
``transmission_fingerprint``) and from the current engine's (``transmission.rs``, ``aceptado_con_errores.rs``,
``recovery.rs``). What the AEAT answers is its real answer (``fixtures/``); only the SaaS's gateway transport is
stood in for (``gateway_answers``).
"""

import datetime as dt
import hashlib

import pytest
from django.utils import timezone, translation
from live.context import system_context
from live.errors import Conflict, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.invoice.models import Invoice
from apps.verifactu import certificates, chain, gateway, queries, xsd
from apps.verifactu.models import (
    AeatRecord,
    Chain,
    Config,
    Event,
    OwnCertificate,
    Record,
    SendControl,
)
import re

from apps.verifactu.tests.conftest import (
    A,
    FIXTURES,
    RECIPIENT,
    aeat_holds,
    answering,
    b64,
    ctx_for,
    deliver,
    make_p12,
    manual,
    paged,
    run,
)

pytestmark = pytest.mark.django_db

ISSUER_NIF = "B12345674"


@pytest.fixture(autouse=True)
def certificate_key(settings):
    """The key that keeps the own certificates, as on a server set up (a test without it says so)."""
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()


def open_production(settings) -> None:
    """What going live needs of the server: ERPlora opened real filing on it, and it has the gateway."""
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"


def create(invoice, ctx=None):
    return run("verifactu.record.create", {"invoice_id": str(invoice.id)}, ctx)


def ticket(price=1000):
    return manual(
        [
            {
                "description": "Cut",
                "quantity": "1",
                "unit_price": price,
                "tax_rate": "21",
            }
        ],
        series_code="TICKET",
    )


def code_of(call) -> str:
    with pytest.raises(Conflict) as refused:
        call()
    return refused.value.code


def outbox(name: str) -> list[dict]:
    return [
        event.payload
        for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")
    ]


# Sealing (VERIFACTU-F13, F14)


def test_an_issued_invoice_is_sealed_at_its_emission_as_the_first_record_of_its_chain(issuer):
    # Invoicing asks by name inside its own emission, with the issuer's session: the issuer seals it.
    invoice = manual(**RECIPIENT)
    assert invoice.verifactu_status == "sealed"
    record = Record.objects.get(invoice_id=invoice.id)
    assert record.created_by == "tester"
    result = create(invoice)
    assert (result.already, result.record.id) == (True, record.id)
    assert (record.record_type, record.sequence, record.environment, record.status) == (
        "alta",
        1,
        "testing",
        "pending",
    )
    assert (record.invoice_number, record.issue_date, record.invoice_type) == (
        invoice.number,
        invoice.issue_date,
        "F1",
    )
    assert (record.issuer_nif, record.issuer_name) == (ISSUER_NIF, "Peluquería Ana SL")
    assert (record.recipient_name, record.recipient_tax_id) == (
        "Talleres Pérez SL",
        "B12345674",
    )
    assert (record.base_amount, record.tax_amount, record.total_amount) == (
        1000,
        210,
        1210,
    )
    assert record.tax_breakdown == Invoice.objects.get(pk=invoice.id).tax_breakdown
    assert record.previous_fingerprint == "" and record.previous_record is None
    assert record.fingerprint == chain.alta_hash(
        issuer_nif=ISSUER_NIF,
        number=invoice.number,
        issue_date=invoice.issue_date,
        invoice_type="F1",
        tax_amount=210,
        total_amount=1210,
        previous_hash="",
        generated_at=record.generated_at,
    )
    assert record.qr_url == chain.qr_url(
        issuer_nif=ISSUER_NIF,
        number=invoice.number,
        issue_date=invoice.issue_date,
        total_amount=1210,
        environment="testing",
    )
    assert result.record.qr_svg.startswith("data:image/svg+xml;base64,")
    assert Chain.objects.get(issuer_nif=ISSUER_NIF, environment="testing").sequence == 1
    assert outbox("verifactu.record.created") == [
        {
            "record_id": str(record.id),
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.number,
            "record_type": "alta",
            "sequence": 1,
            "environment": "testing",
        }
    ]
    assert Event.objects.get().kind == "record_created"


def test_the_generation_time_is_madrids_with_its_offset(issuer):
    record = Record.objects.get(pk=create(ticket()).record.id)
    moment = dt.datetime.fromisoformat(record.generated_at)
    assert moment.utcoffset() in (dt.timedelta(hours=1), dt.timedelta(hours=2))
    assert record.generated_at == chain.format_timestamp(
        timezone.localtime(record.generated_on)
    )


def test_the_next_record_chains_to_the_previous_one(issuer):
    first = Record.objects.get(pk=create(ticket()).record.id)
    second = Record.objects.get(pk=create(ticket(2000)).record.id)
    assert second.sequence == 2
    assert second.previous_record_id == first.id
    assert (
        second.previous_fingerprint,
        second.previous_number,
        second.previous_issue_date,
    ) == (
        first.fingerprint,
        first.invoice_number,
        first.issue_date,
    )


def test_a_record_the_schema_refuses_is_never_sealed(issuer, at_emission):
    # Always validated at sealing: a record that could never leave would block its chain forever.
    at_emission(lambda row: {"tax_breakdown": [{**row.tax_breakdown[0], "regime": "99"}]})
    with pytest.raises(Conflict) as refused:
        ticket()
    assert refused.value.code == "verifactu.invalid_record"
    assert "ClaveRegimen" in str(refused.value)
    assert not Invoice.objects.exists()
    assert not Record.objects.exists()
    assert not Chain.objects.filter(sequence__gt=0).exists()


def test_the_xml_is_built_when_sealed_and_passes_the_schema(issuer):
    # Nothing of it waits for the account: IndicadorMultiplesOT is always «S» (ERPlora serves many taxpayers).
    record = Record.objects.get(pk=create(ticket()).record.id)
    assert record.fingerprint and record.qr_url
    assert record.xml.startswith("<sum1:RegistroAlta>")
    assert "<sum1:PrimerRegistro>S</sum1:PrimerRegistro>" in record.xml
    assert "<sum1:NumeroInstalacion>a</sum1:NumeroInstalacion>" in record.xml
    assert "<sum1:IndicadorMultiplesOT>S</sum1:IndicadorMultiplesOT>" in record.xml
    assert f"<sum1:Huella>{record.fingerprint}</sum1:Huella>" in record.xml
    xsd.validate_record(
        record.xml, obligado_name=record.issuer_name, obligado_nif=record.issuer_nif
    )


def test_the_same_invoice_twice_is_one_record_and_one_number(issuer):
    invoice = ticket()
    first = create(invoice)
    again = create(invoice)
    assert (again.already, again.record.id) == (True, first.record.id)
    by_number = run("verifactu.record.create", {"number": invoice.number})
    assert by_number.record.id == first.record.id
    assert Record.objects.count() == 1
    assert Chain.objects.get().sequence == 1


def test_an_invoice_that_does_not_exist_is_not_found(issuer):
    with pytest.raises(NotFound):
        run("verifactu.record.create", {"number": "NOPE-1"})


def test_whoever_issues_may_record_but_nobody_without_the_permission(issuer):
    invoice = ticket()
    assert create(invoice, ctx_for("hub_employee")).record.sequence == 1
    from live.context import OperationContext

    with pytest.raises(PermissionDenied):
        create(invoice, OperationContext(scope=A, actor="x", permissions=frozenset()))


IMPOSSIBLE = [
    # A quota that does not square with its rate (arithmetic_integrity: «an impossible quota is never sealed»).
    lambda entry: {
        "tax_breakdown": [{**entry, "quota": 500}],
        "tax_amount": 500,
        "total_amount": 1500,
    },
    # The header is not the sum of the breakdown.
    lambda entry: {"tax_amount": 300, "total_amount": 1300},
    # A qualification that charges no tax carrying a quota.
    lambda entry: {
        "tax_breakdown": [{**entry, "qualification": "exempt", "exempt_reason": "E1"}]
    },
    # No description: DescripcionOperacion is mandatory.
    lambda entry: {"description": ""},
    # No breakdown at all.
    lambda entry: {"tax_breakdown": []},
]


@pytest.mark.parametrize("change", IMPOSSIBLE)
def test_an_impossible_record_is_never_sealed_and_its_document_is_not_issued(
    issuer, at_emission, change
):
    # Invoicing asks by name inside its emission: a refusal of VeriFactu would fail again, so it undoes the issue.
    at_emission(lambda row: change(row.tax_breakdown[0]))
    assert code_of(ticket) == "verifactu.impossible_record"
    assert not Invoice.objects.exists()
    assert not Record.objects.exists()
    assert not Chain.objects.filter(sequence__gt=0).exists()


@pytest.mark.parametrize("change", IMPOSSIBLE)
def test_an_impossible_record_is_never_sealed_by_a_later_call_either(
    issuer, invoice_does_not_seal, change
):
    # An invoice issued while VeriFactu could not seal it, whose row changed behind Invoicing's back.
    invoice = ticket()
    entry = Invoice.objects.get(pk=invoice.id).tax_breakdown[0]
    Invoice.objects.filter(pk=invoice.id).update(**change(entry))
    assert code_of(lambda: deliver("invoice.invoice.issued")) == "verifactu.impossible_record"
    assert code_of(lambda: create(invoice)) == "verifactu.impossible_record"
    assert not Record.objects.exists()
    assert not Chain.objects.filter(sequence__gt=0).exists()


def test_a_breakdown_of_more_than_twelve_keys_is_refused_before_sealing(issuer, at_emission):
    # The AEAT admits 12 lines of Desglose; the rest is never dropped in silence.
    entries = [
        {"rate": f"{rate}.00", "base": 1000, "quota": rate * 10}
        for rate in range(1, 14)
    ]
    at_emission(
        lambda row: {
            "tax_breakdown": [{**row.tax_breakdown[0], **entry} for entry in entries],
            "base_amount": 13000,
            "tax_amount": 910,
            "total_amount": 13910,
        }
    )
    with pytest.raises(Conflict) as refused:
        ticket()
    assert refused.value.code == "verifactu.impossible_record"
    assert "13" in str(refused.value)
    assert not Invoice.objects.exists()
    assert not Chain.objects.filter(sequence__gt=0).exists()


def test_a_full_invoice_without_the_customers_tax_id_is_refused_not_downgraded(
    issuer, at_emission
):
    at_emission(lambda row: {"customer_tax_id": ""})
    assert code_of(lambda: manual(**RECIPIENT)) == "verifactu.recipient_required"
    assert not Invoice.objects.exists()
    assert not Record.objects.exists()


def test_a_rectifying_invoice_is_an_alta_by_differences_naming_what_it_rectifies(
    issuer
):
    original = manual(**RECIPIENT)
    create(original)
    rect = run(
        "invoice.invoice.rectify", {"number": original.number, "reason": "Wrong price"}
    ).invoice
    record = Record.objects.get(pk=create(rect).record.id)
    assert (record.record_type, record.invoice_type, record.rectification_kind) == (
        "alta",
        "R1",
        "I",
    )
    assert record.rectified == [
        {
            "issuer_nif": ISSUER_NIF,
            "number": original.number,
            "issue_date": original.issue_date.isoformat(),
        }
    ]
    assert (record.total_amount, record.description) == (-1210, "Wrong price")
    assert (
        "<sum1:TipoRectificativa>I</sum1:TipoRectificativa><sum1:FacturasRectificadas>"
        in record.xml
    )
    xsd.validate_record(
        record.xml, obligado_name=record.issuer_name, obligado_nif=ISSUER_NIF
    )


def test_a_full_invoice_replacing_a_ticket_declares_the_ticket(issuer):
    small = ticket()
    create(small)
    full = run(
        "invoice.invoice.substitute", {"number": small.number, **RECIPIENT}
    ).invoice
    record = Record.objects.get(pk=create(full).record.id)
    assert record.invoice_type == "F3"
    assert record.substituted == [
        {
            "issuer_nif": ISSUER_NIF,
            "number": small.number,
            "issue_date": small.issue_date.isoformat(),
        }
    ]
    assert "<sum1:FacturasSustituidas>" in record.xml


def test_production_has_its_own_chain_and_the_real_sites_qr(issuer, settings):
    open_production(settings)
    create(ticket())
    # In production with its way to the AEAT (approved authorisation and the live option).
    Config.objects.filter().update(
        environment="production", representation_status="approved", live_paid=True
    )
    record = Record.objects.get(pk=create(ticket(2000)).record.id)
    assert (record.environment, record.sequence, record.previous_fingerprint) == (
        "production",
        1,
        "",
    )
    assert record.qr_url.startswith("https://www2.agenciatributaria.gob.es/")


# Correcting and cancelling (VERIFACTU-F24, F30)


def test_a_rejected_registration_is_corrected_with_a_new_one_the_aeat_does_not_hold_yet(
    issuer
):
    # §9.1.3 «alta por rechazo»: the initial alta was rejected, so the invoice is not in the AEAT: S + X.
    record = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=record.id).update(status="rejected", aeat_code="1100")
    result = run("verifactu.record.correct", {"invoice_number": record.invoice_number})
    new = Record.objects.get(pk=result.record.id)
    assert (new.correction, new.previous_rejection, new.corrects_id, new.sequence) == (
        True,
        "X",
        record.id,
        2,
    )
    assert new.previous_fingerprint == record.fingerprint
    assert (
        "<sum1:Subsanacion>S</sum1:Subsanacion><sum1:RechazoPrevio>X</sum1:RechazoPrevio>"
        in new.xml
    )
    xsd.validate_record(new.xml, obligado_name=new.issuer_name, obligado_nif=new.issuer_nif)
    record.refresh_from_db()
    assert (record.status, record.aeat_code) == ("rejected", "1100")  # never modified


def test_a_rejected_correction_of_a_rejected_registration_still_says_the_aeat_does_not_hold_it(
    issuer
):
    record = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=record.id).update(status="rejected")
    first = run("verifactu.record.correct", {"record_id": str(record.id)}).record.id
    Record.objects.filter(pk=first).update(status="rejected")
    second = Record.objects.get(pk=run("verifactu.record.correct", {"record_id": str(first)}).record.id)
    assert (second.corrects_id, second.previous_rejection) == (first, "X")


def test_a_rejected_correction_of_a_record_the_aeat_holds_says_there_was_a_rejection(
    issuer
):
    # The AEAT holds the invoice (accepted with errors); its correction was rejected: the next one says S.
    record = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=record.id).update(status="accepted_with_errors")
    first = run("verifactu.record.correct", {"record_id": str(record.id)}).record.id
    Record.objects.filter(pk=first).update(status="rejected")
    second = Record.objects.get(pk=run("verifactu.record.correct", {"record_id": str(first)}).record.id)
    assert second.previous_rejection == "S"
    assert (
        "<sum1:Subsanacion>S</sum1:Subsanacion><sum1:RechazoPrevio>S</sum1:RechazoPrevio>"
        in second.xml
    )


def test_an_accepted_with_errors_record_is_corrected_without_a_previous_rejection(
    issuer
):
    record = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=record.id).update(status="accepted_with_errors")
    new = Record.objects.get(
        pk=run("verifactu.record.correct", {"record_id": str(record.id)}).record.id
    )
    assert new.previous_rejection == "N"
    assert "<sum1:Subsanacion>S</sum1:Subsanacion><sum1:TipoFactura>" in new.xml


@pytest.mark.parametrize("status", ["pending", "sent", "accepted"])
def test_only_a_rejected_or_accepted_with_errors_record_is_corrected(issuer, status):
    record = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=record.id).update(status=status)
    assert (
        code_of(lambda: run("verifactu.record.correct", {"record_id": str(record.id)}))
        == "verifactu.cannot_correct"
    )


def test_a_record_is_corrected_once(issuer):
    record = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=record.id).update(status="rejected")
    run("verifactu.record.correct", {"record_id": str(record.id)})
    assert (
        code_of(lambda: run("verifactu.record.correct", {"record_id": str(record.id)}))
        == "verifactu.cannot_correct"
    )


def test_the_manager_may_not_correct_nor_cancel(issuer):
    record = Record.objects.get(pk=create(ticket()).record.id)
    with pytest.raises(PermissionDenied):
        run(
            "verifactu.record.correct",
            {"record_id": str(record.id)},
            ctx_for("hub_manager"),
        )
    with pytest.raises(PermissionDenied):
        run(
            "verifactu.record.cancel",
            {"record_id": str(record.id), "reason": "x"},
            ctx_for("hub_manager"),
        )


def test_an_invoice_issued_by_error_is_cancelled_with_a_chained_anulacion(
    issuer
):
    alta = Record.objects.get(pk=create(ticket()).record.id)
    result = run(
        "verifactu.record.cancel",
        {"invoice_number": alta.invoice_number, "reason": "Duplicated ticket"},
    )
    anulacion = Record.objects.get(pk=result.record.id)
    assert (anulacion.record_type, anulacion.cancels_id, anulacion.sequence) == (
        "anulacion",
        alta.id,
        2,
    )
    assert (anulacion.base_amount, anulacion.tax_amount, anulacion.total_amount) == (
        None,
        None,
        None,
    )
    assert anulacion.fingerprint == chain.anulacion_hash(
        issuer_nif=ISSUER_NIF,
        number=alta.invoice_number,
        issue_date=alta.issue_date,
        previous_hash=alta.fingerprint,
        generated_at=anulacion.generated_at,
    )
    assert anulacion.xml.startswith("<sum1:RegistroAnulacion>")
    assert anulacion.description == "Duplicated ticket"
    xsd.validate_record(
        anulacion.xml, obligado_name=anulacion.issuer_name, obligado_nif=ISSUER_NIF
    )
    assert (
        code_of(
            lambda: run(
                "verifactu.record.cancel",
                {"record_id": str(alta.id), "reason": "again"},
            )
        )
        == "verifactu.cannot_cancel"
    )


def test_a_cancellation_after_a_rejected_cancellation_says_so(issuer):
    # §9.2.2 «anulación por rechazo»: the invoice is in the AEAT, its earlier anulación was rejected.
    alta = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=alta.id).update(status="accepted")
    first = run("verifactu.record.cancel", {"record_id": str(alta.id), "reason": "Duplicated"}).record.id
    assert Record.objects.get(pk=first).previous_rejection == ""
    assert "RechazoPrevio" not in Record.objects.get(pk=first).xml
    Record.objects.filter(pk=first).update(status="rejected")
    again = Record.objects.get(
        pk=run("verifactu.record.cancel", {"record_id": str(alta.id), "reason": "Duplicated"}).record.id
    )
    assert (again.cancels_id, again.previous_rejection) == (alta.id, "S")
    assert "</sum1:IDFactura><sum1:RechazoPrevio>S</sum1:RechazoPrevio>" in again.xml
    xsd.validate_record(again.xml, obligado_name=again.issuer_name, obligado_nif=again.issuer_nif)


def test_a_rejected_registration_is_not_in_the_aeat_and_is_not_cancelled(issuer):
    alta = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=alta.id).update(status="rejected")
    assert (
        code_of(
            lambda: run(
                "verifactu.record.cancel", {"record_id": str(alta.id), "reason": "x"}
            )
        )
        == "verifactu.cannot_cancel"
    )


# Sending (VERIFACTU-F15, F20, F21, F25)


def test_without_a_gateway_nothing_is_sent_and_nothing_is_accepted(
    issuer, settings
):
    settings.VERIFACTU_GATEWAY_URL = ""
    record = Record.objects.get(pk=create(ticket()).record.id)
    assert (
        code_of(lambda: run("verifactu.record.transmit", {"record_id": str(record.id)}))
        == "verifactu.gateway_unavailable"
    )
    result = run("verifactu.contingency.process")
    assert (result.sent, result.reason) == (0, "gateway_unavailable")
    record.refresh_from_db()
    assert (record.status, record.wait_reason, record.csv) == (
        "pending",
        "gateway_unavailable",
        "",
    )


def test_a_record_that_stops_its_chain_is_told_once_not_at_every_pass(
    issuer, gateway_answers
):
    # A record kept without its XML (sealed before the XML was built at sealing), then changed behind our back:
    # its XML is built when it leaves, and the schema refuses it.
    record = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=record.id).update(
        xml="", tax_breakdown=[{**record.tax_breakdown[0], "regime": "99"}]
    )
    gateway_answers.set(answering())
    for _ in range(3):
        result = run("verifactu.contingency.process")
        assert result.sent == 0
    assert gateway_answers.calls == []
    assert Event.objects.filter(message_key="xml_invalid").count() == 1
    assert Event.objects.filter(message_key="deferred").count() == 1
    record.refresh_from_db()
    assert (record.status, record.wait_reason) == ("pending", "xml_invalid")


def test_a_submission_carries_the_chain_in_order_and_takes_the_aeats_acceptance(
    issuer, gateway_answers
):
    gateway_answers.set(answering())
    first = Record.objects.get(pk=create(ticket()).record.id)
    second = Record.objects.get(pk=create(ticket(2000)).record.id)
    result = run("verifactu.contingency.process")
    assert (result.chains, result.sent, result.accepted, result.waiting) == (1, 2, 2, 0)
    [(path, payload)] = gateway_answers.calls
    assert path == gateway.SUBMIT_PATH
    assert (
        payload["hub"],
        payload["nif"],
        payload["environment"],
        payload["route"],
    ) == ("a", ISSUER_NIF, "testing", "erplora")
    sent = payload["envelope"]
    xsd.validate(sent)
    assert sent.index(first.invoice_number) < sent.index(second.invoice_number)
    # ERPlora presents with its seal for another obligado: it says so; the first send is not late.
    assert (
        "<sum1:Representante><sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon><sum1:NIF>B27593136</sum1:NIF></sum1:Representante>"
        in sent
    )
    assert "Incidencia" not in sent
    for record in (first, second):
        record.refresh_from_db()
        assert (record.status, record.csv, record.attempts) == (
            "accepted",
            "A-82F5RTZ2AQ9N59",
            0,
        )
        assert record.envelope_digest == hashlib.sha256(sent.encode()).hexdigest()
        assert record.transmission_id is not None and record.transmitted_at is not None
    assert first.transmission_id == second.transmission_id
    control = SendControl.objects.get()
    assert control.wait_seconds == 60
    assert control.next_send_at > timezone.now() + dt.timedelta(seconds=50)
    assert outbox("verifactu.record.transmitted")[0]["record_ids"] == [
        str(first.id),
        str(second.id),
    ]


def test_the_aeats_waiting_time_is_respected(issuer, gateway_answers):
    gateway_answers.set(answering())
    create(ticket())
    run("verifactu.contingency.process")
    late = Record.objects.get(pk=create(ticket(2000)).record.id)
    assert run("verifactu.contingency.process").sent == 0
    assert (
        code_of(lambda: run("verifactu.record.transmit", {"record_id": str(late.id)}))
        == "verifactu.aeat_wait"
    )
    SendControl.objects.update(next_send_at=timezone.now() - dt.timedelta(seconds=1))
    assert (
        run(
            "verifactu.record.transmit", {"invoice_number": late.invoice_number}
        ).accepted
        == 1
    )
    assert len(gateway_answers.calls) == 2


def test_accepted_with_errors_is_registered_and_keeps_its_code(
    issuer, gateway_answers
):
    gateway_answers.set(answering("alta_2007_aceptado_con_errores_2026-08-02.xml"))
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    record.refresh_from_db()
    assert (record.status, record.aeat_code, record.csv) == (
        "accepted_with_errors",
        "2007",
        "A-LMD4YBDYE2MVG4",
    )
    [payload] = outbox("verifactu.record.accepted_with_errors")
    assert payload["code"] == "2007" and "total" not in str(payload)


def test_a_duplicate_of_a_record_the_aeat_holds_is_that_record_registered(
    issuer, gateway_answers
):
    gateway_answers.set(answering("alta_3000_duplicado_tras_rechain_2026-08-02.xml"))
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    record.refresh_from_db()
    assert (record.status, record.aeat_code) == ("accepted_with_errors", "2007")


def test_a_rejection_stays_visible_and_leaves_the_queue(
    issuer, gateway_answers
):
    def rejected(payload):
        reply = answering("alta_2007_aceptado_con_errores_2026-08-02.xml")(payload)
        body = reply.aeat_body.replace(">AceptadoConErrores<", ">Incorrecto<").replace(
            ">2007<", ">1189<"
        )
        return gateway.Reply(kind=gateway.ANSWERED, aeat_status=200, aeat_body=body)

    gateway_answers.set(rejected)
    record = Record.objects.get(pk=create(ticket()).record.id)
    result = run("verifactu.contingency.process")
    record.refresh_from_db()
    assert (result.rejected, record.status, record.aeat_code) == (1, "rejected", "1189")
    assert (
        outbox("verifactu.record.rejected")[0]["invoice_number"]
        == record.invoice_number
    )
    assert Event.objects.filter(kind="failed", record=record).exists()
    assert run("verifactu.contingency.process").sent == 0


def test_a_fault_refuses_the_submission_not_its_records(issuer, gateway_answers):
    # A SOAP fault (here 4104, permanent) refuses the SENDING: the AEAT evaluated no record, so none is
    # «rejected» (that would force corrections of records it never saw); they wait, loudly, with their attempt spent.
    body = FIXTURES.joinpath("play_reviewer_seeded_answer_2026-09-23.xml").read_text()
    gateway_answers.set(
        gateway.Reply(kind=gateway.ANSWERED, aeat_status=500, aeat_body=body)
    )
    record = Record.objects.get(pk=create(ticket()).record.id)
    result = run("verifactu.contingency.process")
    assert (result.sent, result.rejected, result.reason) == (1, 0, "aeat_fault")
    assert "4104" in result.message
    record.refresh_from_db()
    assert (record.status, record.attempts, record.wait_reason, record.aeat_code) == (
        "pending",
        1,
        "aeat_fault",
        "",
    )
    assert record.wait_detail.startswith("4104")
    assert record.next_attempt_at > timezone.now()
    assert Event.objects.filter(severity="critical", message_key="deferred").count() == 1
    assert not OutboxEvent.objects.filter(name="verifactu.record.rejected").exists()


def test_a_gateway_that_cannot_be_reached_leaves_it_waiting_longer_each_time(
    issuer, gateway_answers
):
    gateway_answers.set(
        gateway.Reply(kind=gateway.UNREACHABLE, message="connection refused")
    )
    record = Record.objects.get(pk=create(ticket()).record.id)
    result = run("verifactu.contingency.process")
    # Nothing left: never told as «sent».
    assert (result.chains, result.sent, result.reason) == (0, 0, "unreachable")
    assert "connection refused" in result.message
    record.refresh_from_db()
    assert (record.status, record.attempts, record.wait_reason) == (
        "pending",
        1,
        "unreachable",
    )
    assert (
        dt.timedelta(minutes=4)
        < record.next_attempt_at - timezone.now()
        <= dt.timedelta(minutes=5)
    )
    # Not before its time…
    assert run("verifactu.contingency.process").sent == 0
    assert len(gateway_answers.calls) == 1
    # …and then declared as late.
    Record.objects.update(next_attempt_at=timezone.now())
    gateway_answers.set(answering())
    run("verifactu.contingency.process")
    record.refresh_from_db()
    assert (record.status, record.incident) == ("accepted", True)
    assert (
        "<sum1:RemisionVoluntaria><sum1:Incidencia>S</sum1:Incidencia></sum1:RemisionVoluntaria>"
        in gateway_answers.calls[-1][1]["envelope"]
    )


def test_a_request_that_left_without_answer_is_sent_and_goes_again(
    issuer, gateway_answers
):
    gateway_answers.set(gateway.Reply(kind=gateway.UNKNOWN, message="read timeout"))
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    record.refresh_from_db()
    assert (record.status, record.attempts) == ("sent", 1)
    assert (
        code_of(lambda: run("verifactu.record.correct", {"record_id": str(record.id)}))
        == "verifactu.cannot_correct"
    )


def test_a_refusal_of_the_gateway_says_why(issuer, gateway_answers):
    gateway_answers.set(
        gateway.Reply(
            kind=gateway.REFUSED,
            code="verifactu_gateway.nif_mismatch",
            message="Not the declared NIF.",
        )
    )
    record = Record.objects.get(pk=create(ticket()).record.id)
    result = run("verifactu.record.transmit", {"record_id": str(record.id)})
    assert (result.chains, result.sent, result.reason) == (0, 0, "refused")
    assert "Not the declared NIF." in result.message
    record.refresh_from_db()
    assert (record.status, record.wait_reason) == ("pending", "refused")
    assert "Not the declared NIF." in record.wait_detail


# A refusal of the gateway (409/413/422) would be refused again as it is: it waits for a change, never on a timer.


def refuse_once(gateway_answers) -> Record:
    """A record the gateway refused once (it lacks the business's certificate), its backoff long gone."""
    gateway_answers.set(
        gateway.Reply(
            kind=gateway.REFUSED,
            code="no_certificate",
            message="No certificate for this business.",
        )
    )
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    assert len(gateway_answers.calls) == 1
    Record.objects.update(next_attempt_at=timezone.now() - dt.timedelta(days=1))
    record.refresh_from_db()
    return record


def test_a_refusal_of_the_gateway_is_not_tried_again_by_itself(issuer, gateway_answers):
    record = refuse_once(gateway_answers)
    assert (record.status, record.wait_reason) == ("pending", "refused")
    assert "no_certificate" in record.wait_detail

    out = run("verifactu.contingency.process")

    assert len(gateway_answers.calls) == 1
    assert (out.sent, out.waiting, out.reason) == (0, 1, "refused")
    assert "is not sent again by itself" in out.message
    detail = run("verifactu.record.get", {"record_id": str(record.id)})
    assert detail.next_attempt_at is None
    assert "refused" in {wait.code for wait in detail.waiting}


@pytest.mark.parametrize("change", ["route", "certificate", "account"])
def test_a_change_of_the_configuration_puts_a_refused_record_back_in_the_queue(
    issuer, storage, gateway_answers, change
):
    upload()
    record = refuse_once(gateway_answers)
    if change == "route":
        run("verifactu.config.update", {"route": "own"})
    elif change == "certificate":
        upload()
    else:
        run("verifactu.config.sync", {"version": 1, "live_paid": True}, system_context(A))
    gateway_answers.set(answering())

    run("verifactu.contingency.process")

    assert len(gateway_answers.calls) == 2
    record.refresh_from_db()
    assert record.status == "accepted"


def test_an_old_photo_of_the_account_changes_nothing_and_does_not_send_it(
    issuer, gateway_answers
):
    run("verifactu.config.sync", {"version": 5}, system_context(A))
    refuse_once(gateway_answers)
    run("verifactu.config.sync", {"version": 4, "live_paid": True}, system_context(A))

    run("verifactu.contingency.process")

    assert len(gateway_answers.calls) == 1


@pytest.mark.parametrize("by_hand", ["verifactu.record.transmit", "verifactu.contingency.retry"])
def test_sending_it_again_by_hand_presents_a_refused_record(issuer, gateway_answers, by_hand):
    # «Resend to the AEAT» of the admin and «Send now» are verifactu.record.transmit; «Retry» puts it out with the
    # next pass.
    record = refuse_once(gateway_answers)
    gateway_answers.set(answering())

    run(by_hand, {"record_id": str(record.id)})
    run("verifactu.contingency.process")

    assert len(gateway_answers.calls) == 2
    record.refresh_from_db()
    assert record.status == "accepted"


def test_a_record_the_answer_does_not_name_stays_sent(
    issuer, gateway_answers
):
    gateway_answers.set(
        lambda payload: gateway.Reply(
            kind=gateway.ANSWERED,
            aeat_status=200,
            aeat_body=answering()({"envelope": ""}).aeat_body,
        )
    )
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    record.refresh_from_db()
    assert record.status == "sent"


def test_an_unreadable_answer_is_to_retry(issuer, gateway_answers):
    gateway_answers.set(
        gateway.Reply(
            kind=gateway.ANSWERED, aeat_status=503, aeat_body="<html>maintenance</html>"
        )
    )
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    record.refresh_from_db()
    assert (record.status, record.attempts, record.wait_reason) == (
        "pending",
        1,
        "unreachable",
    )


def test_without_a_certificate_the_own_route_cannot_send(
    issuer, gateway_answers
):
    Config.objects.create(route="own")
    record = Record.objects.get(pk=create(ticket()).record.id)
    assert run("verifactu.contingency.process").reason == "own_certificate_missing"
    record.refresh_from_db()
    assert record.wait_reason == "own_certificate_missing"
    assert gateway_answers.calls == []


def test_in_production_erplora_sends_only_with_the_approved_authorisation(
    issuer, gateway_answers, settings
):
    open_production(settings)
    # Sealed while it was approved, revoked behind its back: the gateway could not present it, so it waits.
    Config.objects.create(
        environment="production", representation_status="approved", live_paid=True
    )
    create(ticket())
    Config.objects.update(representation_status="revoked")
    assert run("verifactu.contingency.process").reason == "representation_not_approved"
    assert gateway_answers.calls == []


def test_a_record_already_in_the_aeat_is_not_sent_again(
    issuer, gateway_answers
):
    gateway_answers.set(answering())
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    assert (
        code_of(lambda: run("verifactu.record.transmit", {"record_id": str(record.id)}))
        == "verifactu.not_in_queue"
    )


def test_the_employee_may_not_send(issuer):
    record = Record.objects.get(pk=create(ticket()).record.id)
    with pytest.raises(PermissionDenied):
        run(
            "verifactu.record.transmit",
            {"record_id": str(record.id)},
            ctx_for("hub_employee"),
        )
    with pytest.raises(PermissionDenied):
        run("verifactu.contingency.process", {}, ctx_for("hub_employee"))


def test_the_scheduled_pass_records_nothing_when_there_is_nothing_to_do(
    issuer, gateway_answers
):
    run("verifactu.contingency.process", {}, system_context(A))
    assert not Event.objects.filter(kind="queue_processed").exists()
    assert outbox("verifactu.contingency.processed") == []


# Retrying (VERIFACTU-F22)


def test_retry_puts_the_record_and_its_earlier_ones_out_with_the_next_pass(
    issuer, gateway_answers
):
    gateway_answers.set(gateway.Reply(kind=gateway.UNREACHABLE, message="down"))
    first = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    second = Record.objects.get(pk=create(ticket(2000)).record.id)
    run("verifactu.contingency.retry", {"record_id": str(second.id)})
    first.refresh_from_db()
    assert first.next_attempt_at <= timezone.now()
    assert first.attempts == 1  # kept
    assert outbox("verifactu.contingency.retried") == [{"record_id": str(second.id)}]


def test_retry_refuses_what_is_not_in_the_queue(issuer):
    record = Record.objects.get(pk=create(ticket()).record.id)
    Record.objects.filter(pk=record.id).update(status="accepted")
    assert (
        code_of(
            lambda: run("verifactu.contingency.retry", {"record_id": str(record.id)})
        )
        == "verifactu.not_in_queue"
    )


# The chain (VERIFACTU-F26–F29)


def test_an_intact_chain_validates(issuer):
    for price in (1000, 2000, 3000):
        create(ticket(price))
    result = run("verifactu.chain.validate")
    assert (
        result.valid,
        result.total,
        result.first_invalid_sequence,
        result.issuer_nif,
    ) == (True, 3, None, ISSUER_NIF)
    head = Chain.objects.get()
    assert (head.validation_valid, head.validation_total) == (True, 3)
    assert Event.objects.filter(kind="chain_valid").exists()


def test_a_tampered_record_breaks_the_chain_where_it_was_tampered(issuer):
    for price in (1000, 2000, 3000):
        create(ticket(price))
    Record.objects.filter(sequence=2).update(total_amount=99999)
    result = run("verifactu.chain.validate", {"issuer_nif": ISSUER_NIF})
    assert (result.valid, result.first_invalid_sequence) == (False, 2)
    event = Event.objects.get(kind="chain_broken")
    assert event.severity == "critical"


def test_validating_an_issuer_without_records_says_so(issuer):
    assert code_of(lambda: run("verifactu.chain.validate")) == "verifactu.no_records"


def test_a_manual_anchor_continues_the_chain_of_another_application(issuer):
    result = run(
        "verifactu.chain.recover_manual",
        {
            "fingerprint": "ab" * 32,
            "invoice_number": "OLD-2026-99",
            "issue_date": "2026-10-01",
        },
    )
    assert (result.fingerprint, result.invoice_number, result.found) == (
        "AB" * 32,
        "OLD-2026-99",
        0,
    )
    record = Record.objects.get(pk=create(ticket()).record.id)
    assert (
        record.previous_fingerprint,
        record.previous_number,
        record.previous_issue_date,
    ) == (
        "AB" * 32,
        "OLD-2026-99",
        dt.date(2026, 10, 1),
    )
    assert record.previous_record is None
    assert "<sum1:RegistroAnterior>" in record.xml
    # After an anchor the chain still validates: the anchor is where it starts.
    assert run("verifactu.chain.validate").valid is True


def test_the_chain_is_not_anchored_while_records_wait_to_go_out(issuer):
    create(ticket())
    assert (
        code_of(
            lambda: run(
                "verifactu.chain.recover_manual",
                {
                    "fingerprint": "A" * 64,
                    "invoice_number": "X",
                    "issue_date": "2026-10-01",
                },
            )
        )
        == "verifactu.pending_in_chain"
    )


def test_only_the_owner_recovers_the_chain(issuer):
    with pytest.raises(PermissionDenied):
        run(
            "verifactu.chain.recover_manual",
            {
                "fingerprint": "A" * 64,
                "invoice_number": "X",
                "issue_date": "2026-10-01",
            },
            ctx_for("hub_manager"),
        )


def query_reply(name="consulta_preproduccion_2026-08-01.xml"):
    body = FIXTURES.joinpath(name).read_text()
    return gateway.Reply(kind=gateway.ANSWERED, aeat_status=200, aeat_body=body)


def test_the_aeats_records_are_queried_and_replace_the_last_photo(
    issuer, gateway_answers
):
    AeatRecord.objects.create(
        issuer_nif="B27593136", environment="testing", invoice_number="STALE"
    )
    gateway_answers.set(query_reply())
    result = run(
        "verifactu.aeat.query", {"issuer_nif": "B27593136", "year": 2026, "month": 8}
    )
    assert result.count == 4
    assert not AeatRecord.objects.filter(invoice_number="STALE").exists()
    assert AeatRecord.objects.count() == 4
    path, payload = gateway_answers.calls[-1]
    assert path == gateway.QUERY_PATH
    assert (
        "<sum1:Ejercicio>2026</sum1:Ejercicio><sum1:Periodo>08</sum1:Periodo>"
        in payload["envelope"]
    )
    assert (
        "<sum1:IndicadorRepresentante>S</sum1:IndicadorRepresentante>"
        not in payload["envelope"]
    )  # its own NIF


def test_the_aeats_records_are_queried_page_by_page_to_the_last(
    issuer, gateway_answers
):
    # §6.4.3: at most 10,000 per answer; the next query names the last record of the previous one.
    first = FIXTURES.joinpath("consulta_preproduccion_2026-08-01.xml").read_text()
    second = FIXTURES.joinpath("rotation_consult_2026-09-22.xml").read_text()

    def reply(payload):
        more = "ClavePaginacion" not in payload["envelope"]
        body = paged(first, ("B27593136", "PRU-20260801-0001", "01-08-2026")) if more else second
        return gateway.Reply(kind=gateway.ANSWERED, aeat_status=200, aeat_body=body)

    gateway_answers.set(reply)
    result = run("verifactu.aeat.query", {"issuer_nif": "B27593136", "year": 2026, "month": 8})
    assert result.count == 4 + 44
    assert AeatRecord.objects.count() == 48
    assert len(gateway_answers.calls) == 2
    assert (
        "<con:ClavePaginacion><sum1:IDEmisorFactura>B27593136</sum1:IDEmisorFactura>"
        "<sum1:NumSerieFactura>PRU-20260801-0001</sum1:NumSerieFactura>"
        "<sum1:FechaExpedicionFactura>01-08-2026</sum1:FechaExpedicionFactura></con:ClavePaginacion>"
    ) in gateway_answers.calls[1][1]["envelope"]


def test_an_answer_that_keeps_naming_the_same_page_stops_the_query(
    issuer, gateway_answers
):
    body = paged(
        FIXTURES.joinpath("consulta_preproduccion_2026-08-01.xml").read_text(),
        ("B27593136", "PRU-20260801-0001", "01-08-2026"),
    )
    gateway_answers.set(gateway.Reply(kind=gateway.ANSWERED, aeat_status=200, aeat_body=body))
    assert (
        code_of(lambda: run("verifactu.aeat.query", {"issuer_nif": "B27593136", "year": 2026, "month": 8}))
        == "verifactu.aeat_unreachable"
    )
    assert len(gateway_answers.calls) == 2
    assert not AeatRecord.objects.exists()


def test_the_chain_is_recovered_on_the_last_record_the_aeat_holds(
    issuer, gateway_answers
):
    gateway_answers.set(query_reply())
    result = run("verifactu.chain.recover_from_aeat", {"issuer_nif": "B27593136"})
    assert (result.invoice_number, result.found) == ("PRU-20260801-0004", 4)
    assert (
        result.fingerprint
        == "3056799E8B154276ED2F71108D8570168FD8FE345428C5270459C90AEFBF3696"
    )
    head = Chain.objects.get(issuer_nif="B27593136", environment="testing")
    assert (head.anchor_source, head.last_issue_date) == ("aeat", dt.date(2026, 8, 1))


def test_a_query_refused_by_the_aeat_recovers_nothing(
    issuer, gateway_answers
):
    gateway_answers.set(query_reply("play_reviewer_seeded_answer_2026-09-23.xml"))
    assert (
        code_of(
            lambda: run(
                "verifactu.chain.recover_from_aeat", {"issuer_nif": "B27593136"}
            )
        )
        == "verifactu.aeat_refused"
    )
    assert not Chain.objects.filter(anchor_source="aeat").exists()


def test_without_records_at_the_aeat_there_is_nothing_to_recover(
    issuer, gateway_answers
):
    body = query_reply().aeat_body
    empty = re.sub(
        r"<tikLRRC:RegistroRespuestaConsultaFactuSistemaFacturacion>.*</tikLRRC:RegistroRespuestaConsultaFactuSistemaFacturacion>",
        "",
        body,
        flags=re.DOTALL,
    )
    gateway_answers.set(
        gateway.Reply(kind=gateway.ANSWERED, aeat_status=200, aeat_body=empty)
    )
    assert (
        code_of(
            lambda: run(
                "verifactu.chain.recover_from_aeat", {"issuer_nif": "B27593136"}
            )
        )
        == "verifactu.nothing_to_recover"
    )


def test_without_a_gateway_the_aeat_is_not_asked(issuer, settings):
    settings.VERIFACTU_GATEWAY_URL = ""
    assert (
        code_of(lambda: run("verifactu.aeat.query")) == "verifactu.gateway_unavailable"
    )
    assert (
        code_of(lambda: run("verifactu.chain.recover_from_aeat"))
        == "verifactu.gateway_unavailable"
    )


# A record of the queue that the AEAT may already hold (VERIFACTU-F35)


def left_without_answer(gateway_answers) -> Record:
    """A ticket whose submission left and got no answer: «sent», in the queue."""
    gateway_answers.set(gateway.Reply(kind=gateway.UNKNOWN, message="read timeout"))
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    record.refresh_from_db()
    assert record.status == "sent"
    return record


def test_a_record_the_aeat_already_holds_leaves_the_queue_as_registered(
    issuer, gateway_answers
):
    record = left_without_answer(gateway_answers)
    gateway_answers.set(aeat_holds(record))
    result = run("verifactu.record.reconcile", {"record_id": str(record.id)})
    assert result.held is True
    assert (result.record.id, result.record.status) == (record.id, "accepted")
    record.refresh_from_db()
    assert (record.status, record.wait_reason, record.wait_detail) == ("accepted", "", "")
    assert record.attempts == 1  # the failed attempt is kept
    path, payload = gateway_answers.calls[-1]
    assert path == gateway.QUERY_PATH
    assert (
        f"<sum1:Ejercicio>{record.issue_date:%Y}</sum1:Ejercicio>"
        f"<sum1:Periodo>{record.issue_date:%m}</sum1:Periodo>"
    ) in payload["envelope"]
    assert payload["nif"] == ISSUER_NIF
    event = Event.objects.get(message_key="record_reconciled")
    assert (event.kind, event.record_id, event.actor) == ("accepted", record.id, "tester")
    assert event.message() == (
        f"Invoice {record.invoice_number} was already in the AEAT (Accepted): out of the queue."
    )
    assert outbox("verifactu.record.reconciled") == [
        {
            "record_id": str(record.id),
            "invoice_number": record.invoice_number,
            "status": "accepted",
            "environment": "testing",
        }
    ]


def test_a_record_the_aeat_holds_with_errors_is_accepted_with_errors(
    issuer, gateway_answers
):
    record = left_without_answer(gateway_answers)
    gateway_answers.set(aeat_holds(record, state="AceptadoConErrores"))
    result = run("verifactu.record.reconcile", {"invoice_number": record.invoice_number})
    assert (result.held, result.record.status) == (True, "accepted_with_errors")
    assert Event.objects.get(message_key="record_reconciled").kind == "accepted_with_errors"


def test_a_record_the_aeat_does_not_hold_stays_in_the_queue_untouched(
    issuer, gateway_answers
):
    record = left_without_answer(gateway_answers)
    before = Record.objects.values().get(pk=record.pk)
    gateway_answers.set(aeat_holds())  # the AEAT holds other records, not this one
    result = run("verifactu.record.reconcile", {"record_id": str(record.id)})
    assert (result.held, result.record.status) == (False, "sent")
    after = Record.objects.values().get(pk=record.pk)
    assert {k: v for k, v in after.items() if k != "updated_at"} == {
        k: v for k, v in before.items() if k != "updated_at"
    }
    assert outbox("verifactu.record.reconciled") == []
    assert not Event.objects.filter(message_key="record_reconciled").exists()


def test_only_a_record_of_the_queue_is_reconciled(issuer, gateway_answers):
    gateway_answers.set(answering())
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.record.transmit", {"record_id": str(record.id)})
    calls = len(gateway_answers.calls)
    assert (
        code_of(lambda: run("verifactu.record.reconcile", {"record_id": str(record.id)}))
        == "verifactu.not_in_queue"
    )
    assert len(gateway_answers.calls) == calls


def test_without_a_gateway_a_record_is_not_reconciled(issuer, settings):
    settings.VERIFACTU_GATEWAY_URL = ""
    record = Record.objects.get(pk=create(ticket()).record.id)
    assert (
        code_of(lambda: run("verifactu.record.reconcile", {"record_id": str(record.id)}))
        == "verifactu.gateway_unavailable"
    )


def test_an_employee_may_not_ask_the_aeat_about_a_record(issuer):
    record = Record.objects.get(pk=create(ticket()).record.id)
    with pytest.raises(PermissionDenied):
        run(
            "verifactu.record.reconcile",
            {"record_id": str(record.id)},
            ctx_for("hub_employee"),
        )


# The connection test and the test invoice (VERIFACTU-F10, F11)


def test_the_connection_test_says_what_is_missing_and_presents_nothing(
    issuer, settings
):
    settings.VERIFACTU_GATEWAY_URL = ""
    result = run("verifactu.diagnostic.run")
    assert (result.can_send, result.gateway_configured, result.issuer_ready) == (
        False,
        False,
        True,
    )
    assert "producer_ready" not in type(result).model_fields
    assert {reason.code for reason in result.reasons} == {"gateway_unavailable"}
    assert run("verifactu.diagnostic.last").result.ran_at == result.ran_at
    assert not Record.objects.exists()


def test_the_connection_test_asks_the_gateways_probe(issuer, gateway_answers):
    gateway_answers.set(
        gateway.Reply(kind=gateway.ANSWERED, ready=True, message="Ready.")
    )
    result = run("verifactu.diagnostic.run")
    assert (result.can_send, result.gateway_ready, result.gateway_detail) == (
        True,
        True,
        "Ready.",
    )
    assert gateway_answers.calls[-1][0] == gateway.PROBE_PATH


def test_the_test_invoice_is_a_real_ticket_and_its_record(issuer):
    result = run("verifactu.test_invoice.create")
    invoice = Invoice.objects.get(pk=result.invoice_id)
    assert (invoice.invoice_type, invoice.series_code, invoice.total_amount) == (
        "F2",
        "TICKET",
        121,
    )
    assert result.record.invoice_number == invoice.number
    assert Record.objects.get().invoice_id == invoice.id


def test_the_test_invoice_is_only_for_the_test_environment(issuer):
    Config.objects.update_or_create(singleton=True, defaults={"environment": "production"})
    assert (
        code_of(lambda: run("verifactu.test_invoice.create"))
        == "verifactu.testing_only"
    )


# Configuration (VERIFACTU-F04, F08, F09) and the account's photo


def own_certificate(days: float = 400) -> OwnCertificate:
    """A certificate as an upload leaves it (its material aside: the route only reads its expiry)."""
    return OwnCertificate.objects.create(
        holder="ACME SL",
        holder_tax_id=ISSUER_NIF,
        kind="representative",
        expires_at=timezone.now() + dt.timedelta(days=days),
        sealed_blob=certificates.seal(make_p12(), "secret"),
        uploaded_by="ana",
    )


def test_the_own_route_needs_a_loaded_certificate(issuer):
    assert (
        code_of(lambda: run("verifactu.config.update", {"route": "own"}))
        == "verifactu.no_own_certificate"
    )
    own_certificate()
    assert run("verifactu.config.update", {"route": "own"}).route == "own"
    assert outbox("verifactu.config.changed")


def test_an_expired_certificate_is_no_certificate(issuer):
    own_certificate(days=-1)
    assert (
        code_of(lambda: run("verifactu.config.update", {"route": "own"}))
        == "verifactu.no_own_certificate"
    )


def test_going_live_is_closed_until_erplora_opens_it_on_the_server(issuer, settings):
    settings.VERIFACTU_PRODUCTION_ENABLED = False
    assert (
        code_of(lambda: run("verifactu.config.go_live"))
        == "verifactu.production_closed"
    )


def test_going_live_through_erplora_needs_the_approved_authorisation(issuer, settings):
    open_production(settings)
    assert (
        code_of(lambda: run("verifactu.config.go_live"))
        == "verifactu.representation_not_approved"
    )
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": True, "representation": {"status": "approved"}},
        system_context(A),
    )
    config = run("verifactu.config.go_live")
    assert config.environment == "production" and config.production_since is not None


def test_going_live_needs_the_live_option_in_the_plan(issuer, settings):
    open_production(settings)
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": False, "representation": {"status": "approved"}},
        system_context(A),
    )
    assert code_of(lambda: run("verifactu.config.go_live")) == "verifactu.live_option_unpaid"
    assert Config.objects.get().environment == "testing"


def test_going_live_with_the_own_certificate_needs_no_live_option(issuer, settings):
    # The old Hub's an_own_certificate_needs_no_grant_to_go_live: the own route goes live with its valid
    # certificate alone; the live option of the plan is ERPlora filing for the business.
    open_production(settings)
    own_certificate()
    run("verifactu.config.update", {"route": "own"})
    assert run("verifactu.config.go_live").environment == "production"


def test_in_production_erplora_takes_over_only_with_the_live_option(issuer, settings):
    open_production(settings)
    own_certificate()
    run("verifactu.config.update", {"route": "own"})
    run("verifactu.config.go_live")
    run(
        "verifactu.config.sync",
        {"version": 1, "representation": {"status": "approved"}},
        system_context(A),
    )
    erplora = lambda: run("verifactu.config.update", {"route": "erplora"})  # noqa: E731
    assert code_of(erplora) == "verifactu.live_option_unpaid"
    run("verifactu.config.sync", {"version": 2, "live_paid": True}, system_context(A))
    assert erplora().route == "erplora"


def test_going_live_with_an_expired_own_certificate_is_refused(issuer, settings):
    open_production(settings)
    own_certificate()
    run("verifactu.config.update", {"route": "own"})
    OwnCertificate.objects.update(expires_at=timezone.now() - dt.timedelta(days=1))
    assert code_of(lambda: run("verifactu.config.go_live")) == "verifactu.no_own_certificate"
    assert Config.objects.get().environment == "testing"


@pytest.mark.parametrize("status", ["past_due", "suspended"])
def test_going_live_needs_an_active_business(issuer, settings, status):
    open_production(settings)
    run(
        "verifactu.config.sync",
        {
            "version": 1,
            "live_paid": True,
            "hub_status": status,
            "representation": {"status": "approved"},
        },
        system_context(A),
    )
    assert code_of(lambda: run("verifactu.config.go_live")) == "verifactu.hub_not_active"


def test_a_demo_hub_never_goes_live(issuer, settings, monkeypatch):
    # The old Hub's go_live: «a demo cannot» (fiscal.go_live_forbidden), right after a closed server. Whether a hub
    # is a demo is the platform's to say (base.operations.is_demo_hub), never this app's.
    from base import operations as platform

    open_production(settings)
    monkeypatch.setattr(platform, "is_demo_hub", lambda scope: scope == A)
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": True, "representation": {"status": "approved"}},
        system_context(A),
    )
    with pytest.raises(Conflict) as refused:
        run("verifactu.config.go_live")
    assert refused.value.code == "verifactu.go_live_forbidden"
    assert Config.objects.get().environment == "testing"
    assert [reason.code for reason in run("verifactu.config.get").live_blockers] == [
        "go_live_forbidden"
    ]
    with translation.override("es"):
        blockers = run("verifactu.config.get", ctx=ctx_for(language="es")).live_blockers
    assert blockers[0].message.startswith("es un negocio de demostración")


def test_going_live_is_never_open_in_pre(issuer, settings):
    settings.ERPLORA_ENVIRONMENT = "pre"
    open_production(settings)
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": True, "representation": {"status": "approved"}},
        system_context(A),
    )
    assert code_of(lambda: run("verifactu.config.go_live")) == "verifactu.production_closed"


def live_through_erplora() -> None:
    """In production through ERPlora with everything it needs (approved authorisation, live option)."""
    run(
        "verifactu.config.sync",
        {"version": 2, "live_paid": True, "representation": {"status": "approved"}},
        system_context(A),
    )
    run("verifactu.config.go_live")


def close_the_way(problem: str) -> None:
    """What takes the way to the AEAT away from a business already in production, behind its back."""
    if problem == "live_option_unpaid":
        run("verifactu.config.sync", {"version": 3, "live_paid": False}, system_context(A))
    elif problem == "representation_not_approved":
        run(
            "verifactu.config.sync",
            {"version": 3, "representation": {"status": "revoked"}},
            system_context(A),
        )
    else:
        OwnCertificate.objects.update(expires_at=timezone.now() - dt.timedelta(days=1))


@pytest.mark.parametrize(
    "problem",
    ["live_option_unpaid", "representation_not_approved", "own_certificate_missing"],
)
def test_in_production_without_a_way_to_the_aeat_nothing_new_is_sealed(
    issuer, settings, problem
):
    # Working-rules §15: in production nothing is charged that can never reach the AEAT (the old Hub's
    # enforce_fiscal_road, HUB-1935). The refusal carries the route's own code and undoes the whole issue.
    open_production(settings)
    if problem == "own_certificate_missing":
        own_certificate()
        run("verifactu.config.update", {"route": "own"})
        run("verifactu.config.go_live")
    else:
        live_through_erplora()
    ticket()
    close_the_way(problem)
    with pytest.raises(Conflict) as refused:
        ticket()
    assert refused.value.code == f"verifactu.{problem}"
    assert str(refused.value).startswith("Nothing was issued")
    assert (Invoice.objects.count(), Record.objects.count()) == (1, 1)
    assert Chain.objects.get(environment="production").sequence == 1


def test_in_testing_a_missing_way_never_refuses_a_sale(issuer):
    Config.objects.create(route="own")
    record = Record.objects.get(pk=create(ticket()).record.id)
    assert (record.environment, record.status) == ("testing", "pending")


def test_the_reaction_seals_an_invoice_issued_before_the_way_closed(
    issuer, settings, invoice_does_not_seal
):
    # The old Hub let the relay deliver a chain already open: the document exists, so its record is sealed
    # and waits rather than the document going undeclared.
    open_production(settings)
    live_through_erplora()
    invoice = ticket()
    close_the_way("representation_not_approved")
    result = deliver("invoice.invoice.issued")
    assert (result.already, result.record.invoice_id) == (False, invoice.id)
    assert Record.objects.get().environment == "production"


def test_losing_the_live_option_in_production_refuses_new_sales_and_sends_what_was_sealed(
    issuer, gateway_answers, settings
):
    # Review Focus 3: it does not go back to testing (it has production records); new sales are not sealed
    # (409 live_option_unpaid) and Settings says so; what was sealed while it could goes out: the option is
    # the plan's, the record is already the AEAT's (every ticket with a QR reaches it).
    open_production(settings)
    live_through_erplora()
    record = Record.objects.get(pk=create(ticket()).record.id)
    close_the_way("live_option_unpaid")
    assert code_of(ticket) == "verifactu.live_option_unpaid"
    gateway_answers.set(answering())
    result = run("verifactu.contingency.process")
    record.refresh_from_db()
    assert (result.sent, record.status, record.environment) == (1, "accepted", "production")
    config = run("verifactu.config.get")
    assert (config.environment, config.reasons) == ("production", [])
    assert config.issue_blocker.code == "live_option_unpaid"
    assert queries.blockers(Config.objects.get(), "production") == []


def test_going_live_needs_the_issuer(settings, db):
    open_production(settings)
    assert (
        code_of(lambda: run("verifactu.config.go_live")) == "verifactu.issuer_missing"
    )


def test_back_to_testing_until_the_first_production_record(issuer, settings):
    open_production(settings)
    run(
        "verifactu.config.sync",
        {"version": 1, "live_paid": True, "representation": {"status": "approved"}},
        system_context(A),
    )
    run("verifactu.config.go_live")
    assert run("verifactu.config.back_to_testing").environment == "testing"
    run("verifactu.config.go_live")
    create(ticket())
    assert (
        code_of(lambda: run("verifactu.config.back_to_testing"))
        == "verifactu.production_has_records"
    )


def test_the_accounts_photo_is_applied_once_per_version(db):
    sync = lambda data: run("verifactu.config.sync", data, system_context(A))  # noqa: E731
    assert sync({"version": 2, "live_paid": True}).applied is True
    assert sync({"version": 2, "live_paid": False}).applied is False
    assert sync({"version": 1, "live_paid": False}).applied is False
    assert Config.objects.get().live_paid is True


def test_the_photo_brings_the_live_option_the_authorisation_and_the_business_status(db):
    sync = lambda data: run("verifactu.config.sync", data, system_context(A))  # noqa: E731
    approved = {"status": "approved", "updated_at": "2026-10-15T10:00:00Z", "reason": ""}
    answer = sync(
        {"version": 7, "live_paid": True, "hub_status": "active", "representation": approved}
    )
    assert (answer.applied, answer.version) == (True, 7)
    config = Config.objects.get()
    assert (
        config.live_paid,
        config.hub_status,
        config.representation_status,
        config.synced_version,
    ) == (True, "active", "approved", 7)
    assert sync({"version": 7, "live_paid": False}).applied is False
    assert sync({"version": 5, "hub_status": "suspended"}).applied is False
    config.refresh_from_db()
    assert (config.live_paid, config.hub_status) == (True, "active")
    assert sync({"version": 8, "hub_status": "past_due"}).applied is True
    config.refresh_from_db()
    # What the photo leaves out stays as it was.
    assert (config.live_paid, config.hub_status, config.representation_status) == (
        True,
        "past_due",
        "approved",
    )


def test_nobody_but_the_system_receives_the_accounts_photo(db):
    with pytest.raises(PermissionDenied):
        run("verifactu.config.sync", {"version": 1}, ctx_for("hub_owner"))


def test_the_configuration_is_the_owners(db):
    with pytest.raises(PermissionDenied):
        run("verifactu.config.update", {"route": "erplora"}, ctx_for("hub_manager"))


# The reaction to Invoicing's notice (the backup when the emission could not seal)


def test_the_invoices_notice_from_the_outbox_seals_its_record(issuer, invoice_does_not_seal):
    invoice = ticket()
    assert invoice.verifactu_status == "unavailable"
    result = deliver("invoice.invoice.issued")
    assert (result.record.invoice_id, result.already) == (invoice.id, False)
    assert deliver("invoice.invoice.issued").already is True


def test_the_notice_of_an_invoice_sealed_at_its_emission_adds_nothing(issuer):
    invoice = ticket()
    sealed = Record.objects.get(invoice_id=invoice.id)
    result = deliver("invoice.invoice.issued")
    assert (result.already, result.record.id) == (True, sealed.id)
    assert Record.objects.count() == 1
    assert Chain.objects.get().sequence == 1


def test_another_notice_is_not_for_verifactu(issuer):
    from apps.verifactu import events

    assert events.react(A, "invoice.invoice.paid", {"invoice_id": "x"}) is None


# The own certificate, uploaded and removed in the Hub (VERIFACTU-F02, F03)


@pytest.fixture
def storage(settings):
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()
    return settings


def upload(p12: bytes | None = None, password: str = "secret", ctx=None):
    return run(
        "verifactu.certificate.upload",
        {"p12_base64": b64(p12 or make_p12()), "password": password},
        ctx,
    )


def own_route(p12: bytes | None = None):
    upload(p12)
    run("verifactu.config.update", {"route": "own"})


def test_upload_stores_the_certificate_sealed_and_reports_its_holder(issuer, storage):
    p12 = make_p12()
    out = upload(p12)
    assert (
        out.own_certificate.loaded,
        out.own_certificate.holder,
        out.own_certificate.holder_tax_id,
        out.own_certificate.kind,
    ) == (True, "ACME SL", ISSUER_NIF, "representative")
    row = OwnCertificate.objects.get()
    assert bytes(row.sealed_blob) != p12 and b"secret" not in bytes(row.sealed_blob)
    assert certificates.open(row.sealed_blob) == (p12, "secret")
    assert row.uploaded_by == "tester"
    assert Event.objects.filter(message_key="certificate_uploaded").exists()
    assert outbox("verifactu.config.changed")
    assert "secret" not in out.model_dump_json()


def test_uploading_again_replaces_the_certificate(issuer, storage):
    upload(make_p12(days=30))
    upload(make_p12(days=700))
    assert OwnCertificate.objects.count() == 1
    assert OwnCertificate.objects.get().expires_at > timezone.now() + dt.timedelta(
        days=600
    )


def test_upload_refuses_a_holder_that_is_not_the_issuer(issuer, storage):
    with pytest.raises(Conflict) as refused:
        upload(make_p12(org_id="VATES-B99999999"))
    assert refused.value.code == "verifactu.certificate_holder_mismatch"
    assert "B99999999" in str(refused.value) and ISSUER_NIF in str(refused.value)
    assert not OwnCertificate.objects.exists()


def test_upload_needs_the_issuer_first(db, storage):
    assert code_of(lambda: upload()) == "verifactu.issuer_missing"


def test_upload_without_storage_key_is_refused_visibly(issuer, settings):
    settings.FISCAL_CERTIFICATE_KEY = ""
    assert code_of(lambda: upload()) == "verifactu.certificate_storage_unavailable"
    assert not OwnCertificate.objects.exists()


@pytest.mark.parametrize(
    ("p12", "password"),
    [
        (make_p12(), "wrong"),
        (make_p12(client_auth=False), "secret"),
        (make_p12(days=-1), "secret"),
        (b"not a certificate", "secret"),
    ],
    ids=["wrong password", "no client authentication", "expired", "not a p12"],
)
def test_upload_refuses_what_cannot_present(issuer, storage, p12, password):
    with pytest.raises(Conflict) as refused:
        upload(p12, password)
    assert refused.value.code == "verifactu.certificate_invalid"
    assert password not in str(refused.value) or password == "secret"
    assert not OwnCertificate.objects.exists()


def test_upload_refuses_what_is_not_base64(issuer, storage):
    refused = code_of(
        lambda: run(
            "verifactu.certificate.upload",
            {"p12_base64": "%%% not base64 %%%", "password": "secret"},
        )
    )
    assert refused == "verifactu.certificate_invalid"


def test_only_who_configures_uploads_and_removes(issuer, storage):
    manager = ctx_for("hub_manager")
    with pytest.raises(PermissionDenied):
        upload(ctx=manager)
    with pytest.raises(PermissionDenied):
        run("verifactu.certificate.remove", {}, manager)


def test_remove_leaves_the_own_route_waiting(
    issuer, storage, gateway_answers
):
    own_route()
    out = run("verifactu.certificate.remove")
    assert out.own_certificate.loaded is False
    assert not OwnCertificate.objects.exists()
    assert queries.route_problem(queries.config_row(), "testing") == "own_certificate_missing"
    assert Event.objects.filter(message_key="certificate_removed").exists()
    create(ticket())
    assert run("verifactu.contingency.process").reason == "own_certificate_missing"
    assert gateway_answers.calls == []


def test_removing_without_a_certificate_changes_nothing(issuer):
    assert run("verifactu.certificate.remove").own_certificate.loaded is False
    assert not Event.objects.filter(message_key="certificate_removed").exists()


def test_sending_by_own_route_hands_the_certificate_to_the_gateway(
    issuer, storage, gateway_answers
):
    p12 = make_p12()
    own_route(p12)
    gateway_answers.set(answering())
    record = Record.objects.get(pk=create(ticket()).record.id)
    run("verifactu.contingency.process")
    path, sent = gateway_answers.calls[-1]
    assert path == gateway.SUBMIT_PATH
    assert sent["route"] == "own"
    assert sent["certificate"] == {"p12_base64": b64(p12), "password": "secret"}
    record.refresh_from_db()
    assert record.status == "accepted"


def test_erplora_route_never_hands_a_certificate(
    issuer, storage, gateway_answers
):
    upload()
    gateway_answers.set(answering())
    create(ticket())
    run("verifactu.contingency.process")
    assert "certificate" not in gateway_answers.calls[-1][1]


def test_an_unreadable_certificate_keeps_the_record_waiting(
    issuer, storage, gateway_answers
):
    own_route()
    record = Record.objects.get(pk=create(ticket()).record.id)
    storage.FISCAL_CERTIFICATE_KEY = certificates.generate_key()  # rotated
    out = run("verifactu.contingency.process")
    assert (out.sent, out.reason) == (0, "own_certificate_unreadable")
    record.refresh_from_db()
    assert (record.status, record.wait_reason) == ("pending", "own_certificate_unreadable")
    assert gateway_answers.calls == []
    detail = run("verifactu.record.get", {"record_id": str(record.id)})
    assert "own_certificate_unreadable" in {wait.code for wait in detail.waiting}
    assert (
        code_of(lambda: run("verifactu.record.transmit", {"record_id": str(record.id)}))
        == "verifactu.own_certificate_unreadable"
    )


def test_the_probe_and_the_query_carry_the_certificate_on_the_own_route(
    issuer, storage, gateway_answers
):
    p12 = make_p12()
    own_route(p12)
    material = {"p12_base64": b64(p12), "password": "secret"}
    gateway_answers.set(gateway.Reply(kind=gateway.ANSWERED, ready=True, message="Ready."))
    assert run("verifactu.diagnostic.run").gateway_ready is True
    assert gateway_answers.calls[-1][0] == gateway.PROBE_PATH
    assert gateway_answers.calls[-1][1]["certificate"] == material
    gateway_answers.set(query_reply())
    run("verifactu.aeat.query", {"year": 2026, "month": 8})
    assert gateway_answers.calls[-1][0] == gateway.QUERY_PATH
    assert gateway_answers.calls[-1][1]["certificate"] == material


def test_the_connection_test_says_an_unreadable_certificate_and_asks_nothing(
    issuer, storage, gateway_answers
):
    own_route()
    storage.FISCAL_CERTIFICATE_KEY = ""
    result = run("verifactu.diagnostic.run")
    assert result.can_send is False
    assert "own_certificate_unreadable" in {reason.code for reason in result.reasons}
    assert gateway_answers.calls == []
    assert (
        code_of(lambda: run("verifactu.aeat.query", {"year": 2026, "month": 8}))
        == "verifactu.own_certificate_unreadable"
    )
