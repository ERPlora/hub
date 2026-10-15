"""The client of the SaaS's review of the signed authorisation (Anexo I of Convenio 17; VERIFACTU-F05, F06).

The contract (plan 2026-10-15, «Contrato SaaS ↔ Hub», point 2): ``POST {SAAS_INTERNAL_URL}/internal/hubs/{id}/representation``
with the business's documents in base64 → ``201 {status, version, submitted_at}``; its refusals in the single envelope
``{"error": {"code", "message", "fields"?}}``; ``GET /internal/representation/model`` → the blank model, a PDF. Both
signed like every ``/internal`` call, v1 and v2. ``respx`` stands in for the SaaS here; the cases are the old Hub's
(``crates/server/src/representation_grant.rs``: the documents reach the SaaS untouched, the optional ones are left out
when there are none, a refusal never quotes the documents it was carrying).
"""

import datetime as dt
import hashlib
import hmac
import json
import uuid

import httpx
import pytest
import respx

from apps.verifactu import representation

URL = "http://saas.internal:8001"
SECRET = "test-internal-secret"
HUB_ID = uuid.UUID("01920000-0000-7000-8000-000000000abc")
SUBMIT_URL = f"{URL}/internal/hubs/{HUB_ID}/representation"
MODEL_URL = f"{URL}/internal/representation/model"
SIGNED_PDF = "JVBERi0xLjcgZWwgbW9kZWxvIHF1ZSBmaXJtbyBNYW5vbG8="  # %PDF-1.7 el modelo que firmo Manolo
ID_COPY = "JVBERi0xLjcgZWwgRE5JIGRlIE1hbm9sbw=="  # %PDF-1.7 el DNI de Manolo
PAYLOAD = {
    "taxpayer_tax_id": "B12345674",
    "taxpayer_name": "Peluquería Ana SL",
    "signer_tax_id": "12345678Z",
    "signer_name": "Ana Pérez",
    "signer_document_type": "dni",
    "documents": {
        "signed_model": SIGNED_PDF,
        "id_copy": ID_COPY,
        "signature_sample": None,
        "representation_proof": None,
    },
}


@pytest.fixture(autouse=True)
def saas(settings):
    settings.SAAS_INTERNAL_URL = URL
    settings.INTERNAL_SHARED_SECRET = SECRET
    return settings


def v1(timestamp: str, body: bytes) -> str:
    return hmac.new(
        SECRET.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()


def v2(method: str, path: str, timestamp: str, body: bytes) -> str:
    message = f"v2\n{timestamp}\n{method}\n{path}\n".encode() + body
    return hmac.new(SECRET.encode(), message, hashlib.sha256).hexdigest()


def refusal(
    status: int, code: str, message: str = "No.", fields: dict | None = None
) -> httpx.Response:
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return httpx.Response(status, json={"error": error})


@respx.mock
def test_a_201_is_the_submission_under_review_with_its_number():
    respx.post(SUBMIT_URL).mock(
        return_value=httpx.Response(
            201,
            json={
                "status": "submitted",
                "version": 5,
                "submitted_at": "2026-10-15T10:00:00+00:00",
            },
        )
    )
    result = representation.submit(HUB_ID, PAYLOAD)
    assert result == representation.SubmitResult(
        status="submitted",
        version=5,
        submitted_at=dt.datetime(2026, 10, 15, 10, tzinfo=dt.UTC),
    )


@respx.mock
def test_the_documents_reach_the_saas_untouched_and_the_call_is_signed_v1_and_v2():
    route = respx.post(SUBMIT_URL).mock(
        return_value=httpx.Response(
            201, json={"status": "submitted", "version": 1, "submitted_at": None}
        )
    )
    representation.submit(HUB_ID, PAYLOAD, language="es")
    request = route.calls.last.request
    assert json.loads(request.content) == PAYLOAD
    timestamp = request.headers["X-Erplora-Timestamp"]
    assert request.headers["X-Erplora-Signature"] == v1(timestamp, request.content)
    assert request.headers["X-Erplora-Signature-V2"] == v2(
        "POST", f"/internal/hubs/{HUB_ID}/representation", timestamp, request.content
    )
    assert request.headers["Content-Type"] == "application/json"
    # The SaaS words a field's message in the language the Hub asks.
    assert request.headers["Accept-Language"] == "es"


@respx.mock
def test_the_signature_covers_the_path_the_saas_sees_under_a_prefixed_url(saas):
    saas.SAAS_INTERNAL_URL = f"{URL}/saas/"
    route = respx.post(f"{URL}/saas/internal/hubs/{HUB_ID}/representation").mock(
        return_value=httpx.Response(
            201, json={"status": "submitted", "version": 1, "submitted_at": None}
        )
    )
    representation.submit(HUB_ID, PAYLOAD)
    request = route.calls.last.request
    timestamp = request.headers["X-Erplora-Timestamp"]
    assert request.headers["X-Erplora-Signature-V2"] == v2(
        "POST",
        f"/saas/internal/hubs/{HUB_ID}/representation",
        timestamp,
        request.content,
    )


@respx.mock
def test_a_422_is_refused_with_the_saas_code_and_its_fields_as_they_came():
    fields = {"documents.id_copy": "Attach a copy of the signer's identity document."}
    respx.post(SUBMIT_URL).mock(
        return_value=refusal(422, "fiscal.id_copy_required", "Invalid payload", fields)
    )
    with pytest.raises(representation.RepresentationRefused) as refused:
        representation.submit(HUB_ID, PAYLOAD)
    assert (refused.value.status, refused.value.code, refused.value.fields) == (
        422,
        "fiscal.id_copy_required",
        fields,
    )
    assert refused.value.message == "Invalid payload"


@respx.mock
def test_a_body_beyond_the_saas_ceiling_is_refused_with_its_code():
    respx.post(SUBMIT_URL).mock(
        return_value=refusal(413, "fiscal.body_too_large", "32 MB at most.")
    )
    with pytest.raises(representation.RepresentationRefused) as refused:
        representation.submit(HUB_ID, PAYLOAD)
    assert (refused.value.status, refused.value.code, refused.value.fields) == (
        413,
        "fiscal.body_too_large",
        {},
    )


@respx.mock
def test_a_business_the_saas_does_not_know_is_unknown():
    respx.post(SUBMIT_URL).mock(
        return_value=refusal(404, "not_found", "Hub not found.")
    )
    with pytest.raises(representation.HubUnknown):
        representation.submit(HUB_ID, PAYLOAD)


@respx.mock
def test_a_401_is_the_saas_refusing_this_server_not_the_documents():
    respx.post(SUBMIT_URL).mock(
        return_value=refusal(
            401, "unauthorized", "Missing, stale or invalid signature."
        )
    )
    with pytest.raises(representation.SaasUnreachable) as unreachable:
        representation.submit(HUB_ID, PAYLOAD)
    assert unreachable.value.status == 401


@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("slow"),
        httpx.ReadTimeout("slow"),
    ],
)
@respx.mock
def test_no_answer_is_unreachable(failure):
    respx.post(SUBMIT_URL).mock(side_effect=failure)
    with pytest.raises(representation.SaasUnreachable) as unreachable:
        representation.submit(HUB_ID, PAYLOAD)
    assert unreachable.value.status is None


@respx.mock
def test_a_503_is_unreachable():
    respx.post(SUBMIT_URL).mock(return_value=httpx.Response(503, text="busy"))
    with pytest.raises(representation.SaasUnreachable) as unreachable:
        representation.submit(HUB_ID, PAYLOAD)
    assert unreachable.value.status == 503


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(201, text="not json"),
        httpx.Response(201, json=["submitted"]),
        httpx.Response(201, json={"status": "approved", "version": 1}),
        httpx.Response(201, json={"status": "submitted", "version": "5"}),
        httpx.Response(422, text="<html>proxy</html>"),
    ],
)
@respx.mock
def test_an_answer_out_of_contract_is_unreachable(answer):
    respx.post(SUBMIT_URL).mock(return_value=answer)
    with pytest.raises(representation.SaasUnreachable):
        representation.submit(HUB_ID, PAYLOAD)


@respx.mock
def test_a_failure_never_quotes_the_documents_it_was_carrying():
    respx.post(SUBMIT_URL).mock(
        return_value=httpx.Response(500, text=f"boom {SIGNED_PDF} {ID_COPY}")
    )
    with pytest.raises(representation.SaasUnreachable) as unreachable:
        representation.submit(HUB_ID, PAYLOAD)
    said = f"{unreachable.value} {unreachable.value!r}"
    assert SIGNED_PDF not in said and ID_COPY not in said


def test_without_a_saas_url_nothing_is_sent(saas):
    saas.SAAS_INTERNAL_URL = ""
    with pytest.raises(representation.SaasUnreachable):
        representation.submit(HUB_ID, PAYLOAD)
    with pytest.raises(representation.SaasUnreachable):
        representation.model_pdf()


def test_the_upload_waits_long_enough_for_four_documents():
    assert (representation.TIMEOUT.connect, representation.TIMEOUT.read) == (5.0, 60.0)


@respx.mock
def test_the_model_is_the_saas_pdf_fetched_with_a_signed_get():
    route = respx.get(MODEL_URL).mock(
        return_value=httpx.Response(
            200,
            content=b"%PDF-1.4 Anexo I",
            headers={"Content-Type": "application/pdf"},
        )
    )
    assert representation.model_pdf() == b"%PDF-1.4 Anexo I"
    request = route.calls.last.request
    timestamp = request.headers["X-Erplora-Timestamp"]
    assert request.headers["X-Erplora-Signature"] == v1(timestamp, b"")
    assert request.headers["X-Erplora-Signature-V2"] == v2(
        "GET", "/internal/representation/model", timestamp, b""
    )


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(404, json={"error": {"code": "not_found", "message": "No."}}),
        httpx.Response(
            200, content=b"<html>login</html>", headers={"Content-Type": "text/html"}
        ),
        httpx.Response(502, text="bad gateway"),
    ],
)
@respx.mock
def test_a_model_that_is_not_a_pdf_is_not_handed_on(answer):
    respx.get(MODEL_URL).mock(return_value=answer)
    with pytest.raises(representation.SaasUnreachable) as unreachable:
        representation.model_pdf()
    assert unreachable.value.status == answer.status_code


@respx.mock
def test_the_model_without_an_answer_is_unreachable():
    respx.get(MODEL_URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(representation.SaasUnreachable):
        representation.model_pdf()


# The rules the Hub checks before anything crosses the network (the old Hub's ``validate``, with the contract's 5 MB).


@pytest.mark.parametrize(
    ("nif", "company"),
    [
        ("B12345674", True),
        ("A58818501", True),
        ("W0184081H", True),
        ("12345678Z", False),
        ("X1234567L", False),
        ("Y1234567X", False),
        ("Z1234567R", False),
        ("", False),
    ],
)
def test_a_nif_that_starts_with_an_entity_letter_is_a_legal_person(nif, company):
    assert representation.is_legal_person_nif(nif) is company


def test_the_nif_is_normalised_before_its_first_letter_is_read():
    assert representation.normalise_nif(" b-12.345.674 ") == "B12345674"
    assert representation.is_legal_person_nif(" b-12345674") is True


def b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode()


def test_a_pdf_within_the_limit_is_a_document():
    assert representation.document_problem(b64(b"%PDF-1.7 signed")) is None


@pytest.mark.parametrize(
    "value",
    [b64(b"\xff\xd8\xff\xe0 a photo of the sheet"), "not base64 at all!", b64(b"")],
)
def test_what_is_uploaded_has_to_be_a_pdf(value):
    assert representation.document_problem(value) == "not_pdf"


def test_an_oversized_document_is_refused_before_it_crosses_the_network():
    at_limit = b"%PDF" + b"0" * (representation.MAX_DOCUMENT_BYTES - 4)
    assert representation.document_problem(b64(at_limit)) is None
    assert representation.document_problem(b64(at_limit + b"0")) == "too_large"
    # Too long to be 5 MB before anything is decoded.
    assert representation.document_problem("A" * (representation.MAX_DOCUMENT_CHARACTERS + 4)) == "too_large"


def test_the_route_takes_four_documents_at_the_limit_and_the_fields_around_them():
    assert representation.MAX_BODY_BYTES >= 4 * representation.MAX_DOCUMENT_CHARACTERS + 64 * 1024
