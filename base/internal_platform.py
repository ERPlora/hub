"""``/internal/platform/invoices`` is the door to ERPlora's own hub, which issues ERPlora's invoices, signed as the
rest of ``/internal`` (``base.internal``): ``GET …/health`` (200 ``{"status": "ok"}`` or 503 ``{"status":
"unconfigured", "detail"}``), ``POST …`` (the body of the SaaS's ``platform_payload()``; 201, or 200 when it was issued before), ``GET …/{id}`` (its
status) and ``GET …/{id}/pdf`` (its PDF, printed after the read, outside any transaction). Each runs its operation of
Invoicing as the system on the platform hub and answers ``{"status", "qr", "error"}``.

They run in the platform hub's own database (its registry row, made by ``create_platform_hub``), under the name that row
has (``base.platform_hub``).
"""

import json
import logging
from uuid import UUID

from django.db import DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from live.context import Scope, system_context

from base import pdf, registry
from base.internal import _operation_call, _payload_invalid, _unavailable, internal_view, refuse
from base.tenancy.context import HubWithoutDatabase, use_hub
from base.tenancy.identity import HubIdentityMismatch

# Every door of /internal logs as one: the alarms and the tests read ``base.internal``.
logger = logging.getLogger("base.internal")


def _issue_answer(answer) -> dict:
    """The contract's answer: ``{"status", "qr", "error"}`` (``error`` = ``{"code", "message"}`` or null)."""
    return {
        "status": answer.status,
        "qr": answer.qr,
        "error": answer.error.model_dump() if answer.error is not None else None,
    }


def _platform_call(name: str, payload: dict):
    """Runs ``name`` as the system on the platform hub, in its own database: its output, or the response of its
    refusal.

    The platform hub is the registry's row ``registry.platform_hub_row`` with a database of its own, as any business
    (``manage.py create_platform_hub --execute`` makes both): without it, 503 ``base.platform_hub_missing``, saying
    so; a database that is not its own or cannot be reached now, 503 as for any business."""
    hub = registry.platform_hub_row()
    if hub is None or registry.refusal(hub) is not None:
        return None, refuse(
            503,
            "base.platform_hub_missing",
            "ERPlora's platform hub has no database of its own yet: run manage.py create_platform_hub --execute.",
        )
    try:
        with use_hub(hub):
            return _operation_call(name, payload, system_context(Scope("host", hub.slug)))
    except HubIdentityMismatch:
        logger.critical("base.hub_unavailable hub=%s: its database is not its own; %s refused.", hub.slug, name)
        return None, _unavailable()
    except (DatabaseError, HubWithoutDatabase):
        logger.warning("base.hub_unreachable hub=%s: %s could not reach its database now.", hub.slug, name)
        return None, _unavailable()


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
    try:
        printed = pdf.render_pdf(document.html)
    except OSError as missing:
        # WeasyPrint's libraries are missing on this server (the image installs them).
        return refuse(503, "internal.pdf_unavailable", f"The PDF cannot be printed here: {missing}")
    response = HttpResponse(printed, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{document.number}.pdf"'
    return response
