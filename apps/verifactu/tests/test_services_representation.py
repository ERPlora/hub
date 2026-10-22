"""The signed authorisation sent from the module (VERIFACTU-F05, F06): ``verifactu.representation.submit`` and
``verifactu.representation.model``, and what the account's photo tells the Hub about it.

The Hub checks the documents with the SaaS's own rules and codes (the old Hub's ``validate``: the codes are the
contract, hub#1293) before anything crosses the network, and hands them on byte for byte; it keeps none. The state
comes back in the photo (``verifactu.config.sync``), which also tells the Hub its id in ERPlora; the Hub marks the
upload «under review» on the 201 without waiting for it. ``respx`` stands in for the SaaS.
"""

import base64
import json
import uuid

import httpx
import pytest
import respx
from live.context import system_context
from live.errors import Conflict, InvalidPayload, OperationError, PermissionDenied
from live.models import OutboxEvent

from apps.verifactu import representation
from apps.verifactu.models import Config, Event
from apps.verifactu.tests.conftest import A, ISSUER, ctx_for, run

URL = "http://saas.internal:8001"
HUB_ID = uuid.UUID("01920000-0000-7000-8000-000000000abc")
SUBMIT_URL = f"{URL}/internal/hubs/{HUB_ID}/representation"
MODEL_URL = f"{URL}/internal/representation/model"


def pdf(text: str = "signed") -> str:
    return base64.b64encode(f"%PDF-1.7 {text}".encode()).decode()


SIGNED = pdf("el modelo firmado")
ID_COPY = pdf("el DNI de Ana")
PROOF = pdf("la escritura")
SAMPLE = pdf("la muestra de firma")
COMPANY = {
    "signer_tax_id": "12345678Z",
    "signer_name": "Ana Pérez",
    "signer_document_type": "dni",
    "signed_model_base64": SIGNED,
    "id_copy_base64": ID_COPY,
    "representation_proof_base64": PROOF,
}


@pytest.fixture(autouse=True)
def saas(settings):
    settings.SAAS_INTERNAL_URL = URL
    settings.INTERNAL_SHARED_SECRET = "test-internal-secret"
    return settings


def photo(version: int = 1, **block):
    return run(
        "verifactu.config.sync",
        {"version": version, "hub_id": str(HUB_ID), **block},
        system_context(A),
    )


@pytest.fixture
def linked(issuer):
    photo()


@pytest.fixture
def self_employed(db):
    run(
        "invoice.issuer.update",
        {**ISSUER, "legal_name": "Ana Pérez", "tax_id": "12345678Z"},
    )
    photo()


def submitted(version: int = 3) -> httpx.Response:
    return httpx.Response(
        201,
        json={
            "status": "submitted",
            "version": version,
            "submitted_at": "2026-10-15T10:00:00+00:00",
        },
    )


def refusal_of(call) -> InvalidPayload:
    with pytest.raises(InvalidPayload) as refused:
        call()
    return refused.value


def submit(data: dict | None = None, ctx=None):
    return run("verifactu.representation.submit", data or COMPANY, ctx)


# Before anything is sent


@respx.mock
def test_without_the_accounts_photo_the_business_is_not_linked_yet(issuer):
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    with pytest.raises(Conflict) as refused:
        submit()
    assert refused.value.code == "verifactu.hub_unregistered"
    assert not route.called


@respx.mock
def test_without_invoicings_issuer_nothing_is_sent(db):
    photo()
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    with pytest.raises(Conflict) as refused:
        submit()
    assert refused.value.code == "verifactu.issuer_missing"
    assert not route.called


@respx.mock
def test_a_document_over_5_mb_is_refused_before_any_call(linked):
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    huge = base64.b64encode(b"%PDF" + b"0" * representation.MAX_DOCUMENT_BYTES).decode()
    refused = refusal_of(lambda: submit({**COMPANY, "signed_model_base64": huge}))
    assert (refused.status, refused.code) == (422, "fiscal.document_too_large")
    assert set(refused.fields) == {"signed_model_base64"}
    assert not route.called


@respx.mock
def test_the_signed_model_has_to_be_a_pdf(linked):
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    photo_of_it = base64.b64encode(b"\xff\xd8\xff\xe0 a photo").decode()
    refused = refusal_of(
        lambda: submit({**COMPANY, "signed_model_base64": photo_of_it})
    )
    assert refused.code == "fiscal.signed_model_not_pdf"
    refused = refusal_of(lambda: submit({**COMPANY, "id_copy_base64": photo_of_it}))
    assert (refused.code, set(refused.fields)) == (
        "fiscal.document_not_pdf",
        {"id_copy_base64"},
    )
    assert not route.called


@respx.mock
def test_the_signed_model_and_the_identity_copy_are_required(linked):
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    refused = refusal_of(
        lambda: submit({**COMPANY, "signed_model_base64": "", "id_copy_base64": " "})
    )
    # Every broken rule is named, with the first one's code (the SaaS's order).
    assert refused.code == "fiscal.signed_model_required"
    assert set(refused.fields) == {"signed_model_base64", "id_copy_base64"}
    assert not route.called


@respx.mock
def test_a_nie_needs_a_signature_sample(linked):
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    refused = refusal_of(lambda: submit({**COMPANY, "signer_document_type": "nie"}))
    assert (refused.code, set(refused.fields)) == (
        "fiscal.signature_sample_required",
        {"signature_sample_base64"},
    )
    assert not route.called
    route.mock(return_value=submitted())
    submit(
        {**COMPANY, "signer_document_type": "nie", "signature_sample_base64": SAMPLE}
    )
    assert route.called


@respx.mock
def test_a_company_has_to_prove_who_may_sign_for_it(linked):
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    refused = refusal_of(lambda: submit({**COMPANY, "representation_proof_base64": ""}))
    assert refused.code == "fiscal.representation_proof_required"
    refused = refusal_of(
        lambda: submit({**COMPANY, "signer_tax_id": "", "signer_name": ""})
    )
    assert (refused.code, set(refused.fields)) == (
        "fiscal.signer_required",
        {"signer_tax_id", "signer_name"},
    )
    assert not route.called


@respx.mock
def test_a_self_employed_business_signs_itself_and_needs_no_proof(self_employed):
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    submit(
        {
            "signer_document_type": "dni",
            "signed_model_base64": SIGNED,
            "id_copy_base64": ID_COPY,
        }
    )
    sent = json.loads(route.calls.last.request.content)
    assert (sent["signer_tax_id"], sent["signer_name"]) == ("12345678Z", "Ana Pérez")
    assert sent["documents"]["representation_proof"] is None


# What reaches the SaaS and what the Hub keeps


@respx.mock
def test_the_documents_reach_the_saas_as_they_came_with_invoicings_issuer_as_the_taxpayer(
    linked,
):
    route = respx.post(SUBMIT_URL).mock(return_value=submitted())
    submit(ctx=ctx_for(language="es"))
    request = route.calls.last.request
    assert json.loads(request.content) == {
        "taxpayer_tax_id": "B12345674",
        "taxpayer_name": "Peluquería Ana SL",
        "signer_tax_id": "12345678Z",
        "signer_name": "Ana Pérez",
        "signer_document_type": "dni",
        "documents": {
            "signed_model": SIGNED,
            "id_copy": ID_COPY,
            "signature_sample": None,
            "representation_proof": PROOF,
        },
    }
    assert request.headers["Accept-Language"] == "es"


@respx.mock
def test_a_201_marks_it_under_review_and_leaves_its_trace(linked):
    respx.post(SUBMIT_URL).mock(return_value=submitted(3))
    config = submit()
    assert config.representation.status == "submitted"
    assert config.representation.reason == ""
    assert config.representation.updated_at.isoformat() == "2026-10-15T10:00:00+00:00"
    submission = config.representation.submission
    assert (submission.version, submission.document_type, submission.documents) == (
        3,
        "dni",
        ["signed_model", "id_copy", "representation_proof"],
    )
    event = Event.objects.get(message_key="representation_submitted")
    assert event.kind == Event.Kind.CONFIG_CHANGED and event.actor == "tester"
    # Never a document nor a name in the audit trail: what was sent, not its content.
    assert SIGNED not in json.dumps(event.params) and "Ana" not in json.dumps(
        event.params
    )
    assert [
        e.payload for e in OutboxEvent.objects.filter(name="verifactu.config.changed")
    ][-1] == {"fields": ["representation"]}


@respx.mock
def test_a_returned_authorisation_is_sent_again_and_its_note_goes(linked):
    photo(2, representation={"status": "returned", "reason": "Unsigned page 2"})
    respx.post(SUBMIT_URL).mock(return_value=submitted(4))
    config = submit()
    assert (config.representation.status, config.representation.reason) == (
        "submitted",
        "",
    )


@respx.mock
def test_an_approved_authorisation_keeps_filing_while_the_new_one_is_reviewed(linked):
    # The old module's «While we review the new submission, you keep filing with the current one».
    photo(
        2,
        representation={
            "status": "approved",
            "updated_at": "2026-10-01T10:00:00+00:00",
        },
    )
    respx.post(SUBMIT_URL).mock(return_value=submitted(4))
    config = submit()
    assert config.representation.status == "approved"
    assert config.representation.submission.version == 4


@respx.mock
def test_the_saas_refusal_is_said_with_its_code_and_fields_as_they_came(linked):
    fields = {
        "taxpayer_tax_id": "Enter the Spanish tax ID (NIF) of whoever owes the tax."
    }
    respx.post(SUBMIT_URL).mock(
        return_value=httpx.Response(
            422,
            json={
                "error": {
                    "code": "fiscal.taxpayer_tax_id_invalid",
                    "message": "Invalid payload",
                    "fields": fields,
                }
            },
        )
    )
    refused = refusal_of(submit)
    assert (refused.status, refused.code, refused.fields) == (
        422,
        "fiscal.taxpayer_tax_id_invalid",
        fields,
    )
    assert Config.objects.get().representation_status == "none"
    assert not Event.objects.filter(message_key="representation_submitted").exists()


@respx.mock
def test_a_business_the_saas_does_not_know_is_not_linked(linked):
    respx.post(SUBMIT_URL).mock(
        return_value=httpx.Response(
            404, json={"error": {"code": "not_found", "message": "No."}}
        )
    )
    with pytest.raises(Conflict) as refused:
        submit()
    assert refused.value.code == "verifactu.hub_unregistered"


@pytest.mark.parametrize(
    "answer",
    [
        {"side_effect": httpx.ConnectError("refused")},
        {"return_value": httpx.Response(503, text="busy")},
        {
            "return_value": httpx.Response(
                401, json={"error": {"code": "unauthorized", "message": "No."}}
            )
        },
    ],
)
@respx.mock
def test_without_the_saas_it_is_unavailable_and_nothing_changes(linked, answer):
    respx.post(SUBMIT_URL).mock(**answer)
    with pytest.raises(OperationError) as failed:
        submit()
    assert (failed.value.status, failed.value.code) == (
        503,
        "verifactu.saas_unreachable",
    )
    assert Config.objects.get().representation_status == "none"


def test_only_who_configures_verifactu_sends_it(linked):
    with pytest.raises(PermissionDenied):
        submit(ctx=ctx_for("hub_employee"))


# The photo


def test_the_photo_tells_the_hub_its_id_in_erplora(issuer):
    assert run("verifactu.config.get").representation.linked is False
    photo(1)
    assert Config.objects.get().hub_id == HUB_ID
    assert run("verifactu.config.get").representation.linked is True
    other = uuid.UUID("01920000-0000-7000-8000-000000000def")
    run(
        "verifactu.config.sync", {"version": 1, "hub_id": str(other)}, system_context(A)
    )
    assert (
        Config.objects.get().hub_id == HUB_ID
    )  # an older or equal photo changes nothing


def test_a_change_of_state_in_the_photo_goes_to_the_history(issuer):
    photo(
        1,
        representation={
            "status": "submitted",
            "updated_at": "2026-10-01T10:00:00+00:00",
        },
    )
    photo(
        2,
        representation={
            "status": "returned",
            "updated_at": "2026-10-02T10:00:00+00:00",
            "reason": "Blurry ID",
        },
    )
    photo(
        3,
        representation={
            "status": "returned",
            "updated_at": "2026-10-02T10:00:00+00:00",
            "reason": "Blurry ID",
        },
    )
    history = run("verifactu.config.get").representation.history
    assert [(step.status, step.reason) for step in history] == [
        ("returned", "Blurry ID"),
        ("submitted", ""),
    ]
    assert history[0].at.isoformat() == "2026-10-02T10:00:00+00:00"


def test_the_company_flag_follows_invoicings_issuer(issuer, self_employed):
    assert run("verifactu.config.get").representation.company is False
    run("invoice.issuer.update", ISSUER)
    assert run("verifactu.config.get").representation.company is True


# The blank model


@respx.mock
def test_the_model_is_the_saas_pdf(issuer):
    respx.get(MODEL_URL).mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4 Anexo I",
            headers={"Content-Type": "application/pdf"},
        )
    )
    model = run("verifactu.representation.model")
    assert (model.filename, model.content_type) == (
        "anexo-i-otorgamiento-representacion-erplora.pdf",
        "application/pdf",
    )
    assert base64.b64decode(model.content_base64) == b"%PDF-1.4 Anexo I"


def a_model() -> httpx.Response:
    return httpx.Response(
        200, content=b"%PDF-1.4 Anexo I", headers={"Content-Type": "application/pdf"}
    )


@respx.mock
def test_the_model_comes_with_the_business_of_invoicing(issuer):
    route = respx.get(MODEL_URL).mock(return_value=a_model())
    run("verifactu.representation.model")
    # The taxpayer of the upload (Invoicing's issuer), as the SaaS writes it in the model's blanks; the number goes
    # within the street, as the issuer keeps its address. Never a signer: that one is written by hand (saas#1743).
    assert dict(route.calls.last.request.url.params) == {
        "taxpayer_tax_id": "B12345674",
        "taxpayer_name": "Peluquería Ana SL",
        "municipality": "Madrid",
        "street": "Calle Mayor 1",
    }


@respx.mock
def test_the_model_takes_the_issuer_as_it_is_now(issuer):
    # hub#1306: the business's tax ID saved in Invoicing is the one the model carries, with no wait for the account.
    route = respx.get(MODEL_URL).mock(return_value=a_model())
    run(
        "invoice.issuer.update",
        {**ISSUER, "legal_name": "Ana Pérez", "tax_id": "12345678Z", "city": ""},
    )
    run("verifactu.representation.model")
    assert dict(route.calls.last.request.url.params) == {
        "taxpayer_tax_id": "12345678Z",
        "taxpayer_name": "Ana Pérez",
        "street": "Calle Mayor 1",
    }


@respx.mock
def test_without_an_issuer_the_model_downloads_blank(db):
    route = respx.get(MODEL_URL).mock(return_value=a_model())
    model = run("verifactu.representation.model")
    assert base64.b64decode(model.content_base64) == b"%PDF-1.4 Anexo I"
    assert route.calls.last.request.url.raw_path == b"/internal/representation/model"


@respx.mock
def test_a_detail_the_model_cannot_write_downloads_blank_not_unavailable(issuer):
    route = respx.get(MODEL_URL).mock(
        side_effect=[
            httpx.Response(
                422,
                json={
                    "error": {
                        "code": "invalid_payload",
                        "message": "Invalid payload",
                        "fields": {"street": "Value error, The model cannot write some of these characters."},
                    }
                },
            ),
            a_model(),
        ]
    )
    model = run("verifactu.representation.model")
    assert base64.b64decode(model.content_base64) == b"%PDF-1.4 Anexo I"
    assert "street" not in dict(route.calls.last.request.url.params)
    assert dict(route.calls.last.request.url.params)["taxpayer_tax_id"] == "B12345674"


@respx.mock
def test_without_the_saas_the_model_is_unavailable(issuer):
    respx.get(MODEL_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(OperationError) as failed:
        run("verifactu.representation.model")
    assert (failed.value.status, failed.value.code) == (
        503,
        "verifactu.saas_unreachable",
    )


def test_only_who_configures_verifactu_downloads_the_model(issuer):
    with pytest.raises(PermissionDenied):
        run("verifactu.representation.model", ctx=ctx_for("hub_employee"))
