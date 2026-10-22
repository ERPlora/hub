"""The client of the SaaS's review of the signed authorisation (Anexo I of Convenio 17; VERIFACTU-F05, F06).

ERPlora files a business's records with the AEAT on its behalf only with its signed «otorgamiento de
representación». The business downloads the model here, its details already in, signs it away from the screen and uploads it with
the signer's identity document; a person at ERPlora reviews it in the SaaS (``fiscal/``), and its state comes back
in the account's photo (``verifactu.config.sync``). The Hub keeps none of the documents: it checks them and hands
them on byte for byte, as the old Hub did (``crates/server/src/representation_grant.rs``).

Two doors of the SaaS (plan 2026-10-15, «Contrato SaaS ↔ Hub», point 2), signed like every ``/internal`` call:
``X-Erplora-Timestamp``, ``X-Erplora-Signature`` (v1, ``base.auth.sign``: the body) and ``X-Erplora-Signature-V2``
(v2, ``base.internal.sign_v2``: method, path and body) with ``INTERNAL_SHARED_SECRET``:

- ``POST /internal/hubs/{id}/representation`` with ``{"taxpayer_tax_id", "taxpayer_name", "signer_tax_id",
  "signer_name", "signer_document_type", "documents": {"signed_model", "id_copy", "signature_sample",
  "representation_proof"}}`` (base64; the optional ones ``null``) → ``201 {"status": "submitted", "version",
  "submitted_at"}``;
- ``GET /internal/representation/model?taxpayer_tax_id=…&taxpayer_name=…&municipality=…&street=…&number=…`` → the
  model, ``application/pdf``, with the business written in its blanks (the SaaS's ``fiscal.schemas.ModelQueryIn``,
  every field optional; a blank one stays dotted). Only v2 covers a query, so it signs the path with its query, as
  the SaaS's ``get_full_path()`` reads it. A value the model cannot write (422 ``invalid_payload`` naming it) is
  dropped and the model asked for once more, so it downloads with that blank for the business to fill in by hand.

How a call ended: ``SubmitResult``; ``RepresentationRefused`` (400, 413 or 422 with the contract's envelope: the
documents as they are will not do, its ``fiscal.*`` code and its ``fields`` kept to be shown); ``HubUnknown`` (404:
the SaaS knows no such business); ``SaasUnreachable`` (no connection, a timeout, a 401, a 5xx or an answer out of
contract: nothing the business can fix). ``httpx``: 5 s to connect and 60 s to read, room for four documents of
5 MB. No message quotes what the request carried: a signed document and the scan of an identity card.
"""

import base64
import binascii
import datetime as dt
import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlencode
from uuid import UUID

import httpx
from django.conf import settings

from base.auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign
from base.internal import SIGNATURE_V2_HEADER, sign_v2

logger = logging.getLogger(__name__)

SUBMIT_PATH = "/internal/hubs/{hub_id}/representation"
MODEL_PATH = "/internal/representation/model"
#: The business's details the SaaS writes in the model's blanks (its ``ModelQueryIn``), in the query.
MODEL_FIELDS = ("taxpayer_tax_id", "taxpayer_name", "municipality", "street", "number")
TIMEOUT = httpx.Timeout(60.0, connect=5.0)
#: The statuses whose contract error is about the documents, not about this server.
REFUSALS = (400, 413, 422)
PDF_MAGIC = b"%PDF"
#: At most this many bytes per document, decoded (the contract; the old Hub took 10 MB).
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
#: Base64 of ``MAX_DOCUMENT_BYTES``: anything longer is too large before decoding it.
MAX_DOCUMENT_CHARACTERS = 4 * -(-MAX_DOCUMENT_BYTES // 3)
#: What the upload's body may weigh: four documents at the limit in base64 and the JSON around them (the SaaS's own
#: ceiling, ``fiscal.internal.MAX_BODY_BYTES``).
MAX_BODY_BYTES = 32 * 1024 * 1024
#: The first letters of a Spanish NIF that belong to an entity, not a person (the AEAT's, as the SaaS's
#: ``billing.nif``): a company signs through whoever its deeds name, so the proof of that travels too.
LEGAL_PERSON_LETTERS = frozenset("ABCDEFGHJNPQRSUVW")


@dataclass(frozen=True)
class SubmitResult:
    status: str
    version: int
    submitted_at: dt.datetime | None


class SaasUnreachable(Exception):
    """No answer the contract knows came back; ``status`` is the HTTP status when one did."""

    def __init__(self, detail: str, status: int | None = None) -> None:
        super().__init__(detail)
        self.status = status


class HubUnknown(Exception):
    """The SaaS knows no business with this id (404)."""


class RepresentationRefused(Exception):
    """The SaaS will not file the documents as they are: its ``fiscal.*`` code, message and ``fields``."""

    def __init__(
        self, status: int, code: str, message: str, fields: dict[str, str] | None = None
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.status = status
        self.code = code
        self.message = message
        self.fields = dict(fields or {})


def normalise_nif(value: str | None) -> str:
    """Upper case, without the spaces, dashes and dots people type."""
    return "".join(
        char for char in (value or "") if not char.isspace() and char not in "-."
    ).upper()


def is_legal_person_nif(value: str | None) -> bool:
    nif = normalise_nif(value)
    return bool(nif) and nif[0] in LEGAL_PERSON_LETTERS


def document_problem(value: str) -> str | None:
    """Why a document sent in base64 will not do (``too_large``, ``not_pdf``), or ``None`` when it is a PDF that
    fits. Recognised by its bytes, never by a name or a claimed type."""
    value = value.strip()
    if len(value) > MAX_DOCUMENT_CHARACTERS:
        return "too_large"
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return "not_pdf"
    if len(data) > MAX_DOCUMENT_BYTES:
        return "too_large"
    if not data.startswith(PDF_MAGIC):
        return "not_pdf"
    return None


def _url(path: str) -> str:
    base = str(getattr(settings, "SAAS_INTERNAL_URL", "") or "").strip().rstrip("/")
    if not base:
        raise SaasUnreachable("SAAS_INTERNAL_URL is not set.")
    return f"{base}{path}"


def _headers(method: str, url: str, body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    secret = settings.INTERNAL_SHARED_SECRET
    return {
        TIMESTAMP_HEADER: timestamp,
        SIGNATURE_HEADER: sign(secret, timestamp, body),
        # The path as the SaaS sees it, prefix and query included: the request's target, byte for byte.
        SIGNATURE_V2_HEADER: sign_v2(
            method, httpx.URL(url).raw_path.decode("ascii"), body, timestamp, secret
        ),
    }


def _request(
    method: str, url: str, body: bytes, headers: dict[str, str]
) -> httpx.Response:
    try:
        with httpx.Client(timeout=TIMEOUT, trust_env=False) as client:
            return client.request(method, url, content=body, headers=headers)
    except httpx.HTTPError as error:
        raise SaasUnreachable(
            f"ERPlora's account could not be reached ({type(error).__name__})."
        ) from None


def _envelope(response: httpx.Response) -> dict | None:
    """The contract's ``{"error": {...}}``, or ``None`` when it is not there."""
    try:
        error = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(error, dict) or not isinstance(error.get("code"), str):
        return None
    return error


def _submitted(response: httpx.Response) -> SubmitResult:
    try:
        data = response.json()
    except ValueError:
        data = None
    if (
        not isinstance(data, dict)
        or data.get("status") != "submitted"
        or type(data.get("version")) is not int
    ):
        raise SaasUnreachable(
            "ERPlora's account answered out of contract.", response.status_code
        )
    at = data.get("submitted_at")
    try:
        submitted_at = dt.datetime.fromisoformat(at) if isinstance(at, str) else None
    except ValueError:
        submitted_at = None
    return SubmitResult(
        status="submitted", version=data["version"], submitted_at=submitted_at
    )


def submit(hub_id: UUID, payload: dict, *, language: str = "en") -> SubmitResult:
    """Hand the business's authorisation and its documents to the SaaS for review."""
    url = _url(SUBMIT_PATH.format(hub_id=hub_id))
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    headers = {
        **_headers("POST", url, body),
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": language,
    }
    response = _request("POST", url, body, headers)
    if response.status_code == 201:
        return _submitted(response)
    if response.status_code == 404:
        raise HubUnknown("ERPlora's account knows no such business.")
    error = _envelope(response)
    if response.status_code in REFUSALS and error is not None:
        fields = error.get("fields")
        raise RepresentationRefused(
            response.status_code,
            error["code"],
            str(error.get("message", "")),
            {str(k): str(v) for k, v in fields.items()}
            if isinstance(fields, dict)
            else None,
        )
    raise SaasUnreachable(
        f"ERPlora's account answered HTTP {response.status_code}.", response.status_code
    )


def _model(query: dict[str, str]) -> httpx.Response:
    url = _url(f"{MODEL_PATH}?{urlencode(query)}" if query else MODEL_PATH)
    headers = {**_headers("GET", url, b""), "Accept": "application/pdf"}
    return _request("GET", url, b"", headers)


def _unwritable(response: httpx.Response) -> set[str] | None:
    """The fields a 422 ``invalid_payload`` names (the values the model cannot write), or ``None`` for any other
    answer."""
    error = _envelope(response)
    if response.status_code != 422 or error is None or error["code"] != "invalid_payload":
        return None
    fields = error.get("fields")
    return {str(name) for name in fields} if isinstance(fields, dict) else set()


def model_pdf(taxpayer: dict[str, str] | None = None) -> bytes:
    """The model the business signs (Anexo I of Convenio 17), as the SaaS fills it in: with ``taxpayer`` (the
    ``MODEL_FIELDS`` it has) in the business's blanks, a blank value left dotted. One the model cannot write is
    dropped and the model asked for once more (all of them when the refusal names none of what was sent)."""
    query = {
        name: value.strip()
        for name, value in (taxpayer or {}).items()
        if name in MODEL_FIELDS and value and value.strip()
    }
    response = _model(query)
    unwritable = _unwritable(response) if query else None
    if unwritable is not None:
        logger.warning(
            "verifactu.representation.model_field_unwritable fields=%s",
            ",".join(sorted(unwritable & query.keys())) or "-",
        )
        kept = {name: value for name, value in query.items() if name not in unwritable}
        response = _model(kept if len(kept) < len(query) else {})
    if response.status_code != 200 or not response.content.startswith(PDF_MAGIC):
        raise SaasUnreachable(
            f"ERPlora's account did not hand over the model (HTTP {response.status_code}).",
            response.status_code,
        )
    return response.content
