"""The SaaS's door into the Hub: ``/internal/*``, signed with HMAC-SHA256 and a timestamp (PLAN-SAAS §2, §2.2).

Every call carries ``X-Erplora-Timestamp`` (unix seconds) and up to two hex signatures keyed with the shared
secret, as ``saas-next/accounts/signing.py`` makes them:

- ``X-Erplora-Signature`` (v1) over ``f"{timestamp}.{raw_body}"``: the body only (``base.auth.sign``);
- ``X-Erplora-Signature-V2`` (v2) over ``f"v2\\n{timestamp}\\n{METHOD}\\n{path}\\n"`` + the raw body, ``path`` with its
  query: a signed body cannot be replayed on another route.

A call is heard by v2 when it carries it, and then by v2 alone (naming v2 and failing it is refused even if v1
passes: no downgrade); without v2, by v1. Each signature is checked against every live secret:
``INTERNAL_SHARED_SECRET`` and, during a rotation, ``INTERNAL_SHARED_SECRET_PREVIOUS``. A timestamp more than
``INTERNAL_SIGNATURE_MAX_AGE_SECONDS`` away is refused. The signature is the authentication: the ALB never publishes
``/internal``, so the door answers on any host (the SaaS reaches it by the private name, ``hub.erplora.internal``).

Phase 1 has no registry of hubs (``control/``, phase 2): ``PUT /internal/hubs/{id}/state`` (the photo) names its hub
by ``slug``, and the Hub applies what it already keeps of it, the VeriFactu block, the business's status and its id
in ERPlora (the path's, where the signed authorisation is sent), through ``verifactu.config.sync`` on that hub, as
the system. While the SaaS may still sign v1 only, a body that names the
hub of its path (``hub_id`` or ``id``) must name the same one.

``/internal/platform/invoices`` (contract point 4, PLAN-SAAS §4) is the door to ERPlora's own hub, which issues
ERPlora's invoices: ``GET …/health`` (200 ``{"status": "ok"}`` or 503 ``{"status": "unconfigured", "detail"}``),
``POST …`` (the body of the SaaS's ``platform_payload()``; 201, or 200 when it was issued before), ``GET …/{id}`` (its
status) and ``GET …/{id}/pdf`` (its PDF, printed after the read, outside any transaction). Each runs its operation of
Invoicing as the system on ``PLATFORM_HUB_SLUG`` and answers ``{"status", "qr", "error"}``.
"""

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from functools import wraps
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from live.context import Scope, system_context
from live.errors import OperationError
from live.operations import get as get_operation
from live.slugs import validate_hub_slug
from pydantic import ValidationError

from base.auth import SIGNATURE_HEADER, TIMESTAMP_HEADER, sign

SIGNATURE_V2_HEADER = "X-Erplora-Signature-V2"
#: The business's commercial status as the photo says it (PLAN-SAAS §2.3).
HUB_STATUSES = ("active", "past_due", "suspended")


def sign_v2(method: str, path: str, body: bytes, timestamp: str, secret: str) -> str:
    """The v2 hex signature of ``method`` on ``path`` (with its query) with ``body``, sent at ``timestamp``."""
    message = f"v2\n{timestamp}\n{method.upper()}\n{path}\n".encode() + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def live_secrets() -> tuple[str, ...]:
    """The secrets a call may be signed with: the current one and, during a rotation, the previous."""
    candidates = (
        settings.INTERNAL_SHARED_SECRET,
        getattr(settings, "INTERNAL_SHARED_SECRET_PREVIOUS", ""),
    )
    return tuple(secret for secret in candidates if secret)


def verify_request(request: HttpRequest, *, now: int | None = None) -> bool:
    """Whether ``request`` is signed with a live secret within the window: by v2 if it carries it, else by v1."""
    timestamp = request.headers.get(TIMESTAMP_HEADER)
    if not timestamp or not (timestamp.isascii() and timestamp.isdigit()):
        return False
    sent_at = int(timestamp)
    now = int(time.time()) if now is None else now
    if abs(now - sent_at) > settings.INTERNAL_SIGNATURE_MAX_AGE_SECONDS:
        return False
    stamp = str(sent_at)
    signature_v2 = request.headers.get(SIGNATURE_V2_HEADER)
    expected: Callable[[str], str]
    if signature_v2 is not None:
        signature = signature_v2
        path = request.get_full_path()

        def expected(secret: str) -> str:
            return sign_v2(request.method or "", path, request.body, stamp, secret)
    else:
        signature = request.headers.get(SIGNATURE_HEADER)

        def expected(secret: str) -> str:
            return sign(secret, stamp, request.body)

    if not signature or not signature.isascii():
        return False
    return any(
        hmac.compare_digest(expected(secret), signature) for secret in live_secrets()
    )


def refuse(status: int, code: str, message: str) -> JsonResponse:
    """The error envelope of an internal call (``{"error": {"code", "message"}}``)."""
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def internal_view(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """A view of ``/internal``: no CSRF (no browser), never cached, and 401 ``internal.unsigned`` unless signed."""

    @wraps(view)
    def guarded(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not verify_request(request):
            return refuse(
                401,
                "internal.unsigned",
                "The call is not signed with a live secret within the time window.",
            )
        return view(request, *args, **kwargs)

    return csrf_exempt(never_cache(guarded))


def _payload_invalid(message: str) -> JsonResponse:
    return refuse(422, "internal.payload_invalid", message)


def _names_another_hub(body: dict, hub_id: UUID) -> bool:
    named = body.get("hub_id", body.get("id"))
    if named is None:
        return False
    try:
        return UUID(str(named)) != hub_id
    except ValueError:
        return True


@internal_view
@require_http_methods(["PUT"])
def hub_state(request: HttpRequest, hub_id: UUID) -> HttpResponse:
    """``PUT /internal/hubs/{id}/state``: the SaaS's photo of a business; an older ``version`` changes nothing."""
    try:
        body = json.loads(request.body)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return _payload_invalid("The body is not a JSON object.")
    if _names_another_hub(body, hub_id):
        return refuse(
            422, "internal.hub_mismatch", "The body names another hub than its path."
        )
    try:
        slug = validate_hub_slug(body.get("slug"))
    except ValueError as invalid:
        return refuse(
            422, "internal.slug_invalid", f"The slug names no hub ({invalid})."
        )
    version = body.get("version")
    if type(version) is not int or version < 0:
        return _payload_invalid("The version is a whole number, zero or more.")
    status = body.get("status")
    if status is not None and status not in HUB_STATUSES:
        return _payload_invalid(f"The status is one of {', '.join(HUB_STATUSES)}.")
    block = body.get("verifactu")
    if block is not None and not isinstance(block, dict):
        return _payload_invalid("The verifactu block is a JSON object.")
    live_paid = block.get("live_paid") if block else None
    if live_paid is not None and type(live_paid) is not bool:
        # Read as it came: a string such as "false" never turns into a yes.
        return _payload_invalid("live_paid is true or false.")
    if block is None and status is None:
        return JsonResponse({"applied": False})
    sync = get_operation("verifactu.config.sync")
    try:
        data = sync.input.model_validate(
            {
                **(block or {}),
                "version": version,
                "hub_status": status,
                "hub_id": hub_id,
            }
        )
    except ValidationError as invalid:
        return _payload_invalid(f"The verifactu block is out of contract: {invalid}")
    try:
        answer = sync(system_context(Scope("host", slug)), data)
    except OperationError as failed:
        return JsonResponse(failed.envelope(), status=failed.status)
    return JsonResponse({"applied": answer.applied, "version": answer.version})


# ── ERPlora's own invoices: the door to its platform hub (contract point 4) ──────────────────────────────────────


def _platform_context():
    return system_context(Scope("host", settings.PLATFORM_HUB_SLUG))


def _fields_of(invalid: ValidationError) -> dict[str, str]:
    return {
        ".".join(str(part) for part in error["loc"]) or "body": error["msg"]
        for error in invalid.errors()
    }


def _issue_answer(answer) -> dict:
    """The contract's answer: ``{"status", "qr", "error"}`` (``error`` = ``{"code", "message"}`` or null)."""
    return {
        "status": answer.status,
        "qr": answer.qr,
        "error": answer.error.model_dump() if answer.error is not None else None,
    }


def _platform_call(name: str, payload: dict):
    """Runs ``name`` as the system on the platform hub: its output, or the response of its refusal."""
    op = get_operation(name)
    try:
        data = op.input.model_validate(payload)
    except ValidationError as invalid:
        return None, JsonResponse(
            {
                "error": {
                    "code": "internal.payload_invalid",
                    "message": "The body is out of contract.",
                    "fields": _fields_of(invalid),
                }
            },
            status=422,
        )
    try:
        return op(_platform_context(), data), None
    except OperationError as failed:
        return None, JsonResponse(failed.envelope(), status=failed.status)


@internal_view
@require_http_methods(["GET"])
def platform_invoices_health(request: HttpRequest) -> HttpResponse:
    """``GET /internal/platform/invoices/health``: whether the platform hub can issue ERPlora's invoices now."""
    answer, refused = _platform_call("invoice.invoice.platform_health", {})
    if refused is not None:
        detail = json.loads(refused.content)["error"]["message"]
        return JsonResponse({"status": "unconfigured", "detail": detail}, status=503)
    if not answer.ready:
        return JsonResponse({"status": "unconfigured", "detail": answer.detail}, status=503)
    return JsonResponse({"status": "ok"})


@internal_view
@require_http_methods(["POST"])
def platform_invoice_create(request: HttpRequest) -> HttpResponse:
    """``POST /internal/platform/invoices``: issue ERPlora's invoice; idempotent by its ``id``."""
    try:
        body = json.loads(request.body)
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return _payload_invalid("The body is not a JSON object.")
    answer, refused = _platform_call("invoice.invoice.issue_platform", body)
    if refused is not None:
        return refused
    return JsonResponse(_issue_answer(answer), status=200 if answer.already else 201)


@internal_view
@require_http_methods(["GET"])
def platform_invoice_get(request: HttpRequest, invoice_id: UUID) -> HttpResponse:
    """``GET /internal/platform/invoices/{id}``: how ERPlora's invoice stands."""
    answer, refused = _platform_call("invoice.invoice.platform_status", {"id": str(invoice_id)})
    if refused is not None:
        return refused
    return JsonResponse(_issue_answer(answer))


@internal_view
@require_http_methods(["GET"])
def platform_invoice_pdf(request: HttpRequest, invoice_id: UUID) -> HttpResponse:
    """``GET /internal/platform/invoices/{id}/pdf``: its A4 as PDF, printed once the read is over."""
    document, refused = _platform_call("invoice.invoice.platform_document", {"id": str(invoice_id)})
    if refused is not None:
        return refused
    from apps.invoice.pdf import render_pdf

    try:
        printed = render_pdf(document.html)
    except OSError as missing:
        # WeasyPrint's libraries are missing on this server (the image installs them).
        return refuse(503, "internal.pdf_unavailable", f"The PDF cannot be printed here: {missing}")
    response = HttpResponse(printed, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{document.number}.pdf"'
    return response
