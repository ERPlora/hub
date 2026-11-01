"""The SaaS's door into the Hub: ``/internal/*``, signed with HMAC-SHA256 and a timestamp (PLAN-SAAS §2, §2.2).

Every call carries ``X-Erplora-Timestamp`` (unix seconds) and up to two hex signatures keyed with the shared
secret, as the SaaS makes them (``base.signing``, a port of its ``accounts/signing.py``):

- ``X-Erplora-Signature`` (v1) over ``f"{timestamp}.{raw_body}"``: the body only;
- ``X-Erplora-Signature-V2`` (v2) over ``f"v2\\n{timestamp}\\n{METHOD}\\n{path}\\n"`` + the raw body, ``path`` with its
  query: a signed body cannot be replayed on another route.

A call is heard by v2 when it carries it, and then by v2 alone (naming v2 and failing it is refused even if v1
passes: no downgrade); without v2, by v1. Each signature is checked against every live secret:
``INTERNAL_SHARED_SECRET`` and, during a rotation, ``INTERNAL_SHARED_SECRET_PREVIOUS``. A timestamp more than
``INTERNAL_SIGNATURE_MAX_AGE_SECONDS`` away is refused (401 ``internal.unsigned``). The signature is the
authentication: the ALB never publishes ``/internal``, so the door answers on any host (the SaaS reaches it by the
private name, ``hub.erplora.internal``; ``base.middleware`` leaves ``/internal/`` alone). Every refused signature counts
against the caller (``base.throttle.client_key``): past :data:`SIGNATURE_ATTEMPTS`, its next bad signature is answered
429 ``base.rate_limited`` with ``Retry-After`` until the window of the first refusal ends; a good signature is always
heard (the SaaS never signs wrong: this is for whatever else reaches the door).

The registry of hubs (plan 2026-10-17, §1.5), each route one operation of ``base`` run as the platform on the
registry's scope (``base.registry.REGISTRY_SCOPE``):

- ``PUT /internal/hubs/{id}`` (the SaaS's ``hub_registry()``) → ``base.hub.register``: 202 ``requested`` when it
  creates the row, with a database of its own that the worker makes (``base.tenancy.provision``; round 2026-10-30 of
  PLAN-DB) before it tells the SaaS ``ready``; 202 too for an update while it is being made, 200 for one of a ready
  hub;
- ``GET /internal/hubs/{id}`` → ``base.hub.get``: the row, whose ``status`` ``ready`` the SaaS waits for (``requested``,
  ``creating``, ``migrating``, ``seeding`` or ``failed`` before); never where its database is;
- ``DELETE /internal/hubs/{id}`` → ``base.hub.cancel`` (202; a business with its own database is copied by the
  worker, ``offboarding``); ``POST /internal/hubs/{id}/restore`` → ``base.hub.restore`` (200; 409 ``hub_purged`` when
  it can never come back);
- ``GET /internal/hubs/{id}/dumps`` → ``base.hub.dump_list``: ``{available, dumps: [{id, kind, created_at, bytes,
  url}]}``, the copies of its data (``id``: the key in the bucket), newest first, each link signed for 15 minutes;
  ``available`` false for a business that never gets one (no database of its own); 200 for a business that left too
  (its 410 is its host's door), 404 for one unknown or purged, 503 ``base.dumps_unavailable`` without a bucket;
- ``GET /internal/usage?day=YYYY-MM-DD[&cursor=]`` → ``base.usage.list``: one page of what the businesses with their
  own database used that day (UTC), as the worker measured it that night (``base.usage``): ``{day, hubs: [{id,
  s3_bytes, db_bytes, active_users_1d, active_users_30d}], next_cursor}``; 409 ``usage_not_ready`` before that night
  was measured, 422 ``internal.payload_invalid`` for a day missing or badly written, or a cursor not of its own;
- ``PUT /internal/hubs/{id}/state`` (the photo) → ``base.hub.state_apply``: kept on the row if its ``version`` is
  newer, with its VeriFactu block, the business's status and its id in ERPlora applied through
  ``verifactu.config.sync`` on the hub's slug, and its ``whatsapp`` (the number's state, door 4 of WhatsApp's
  contract) through ``whatsapp_inbox.channel.sync`` with the photo's version, when the app is on in that business,
  and its ``members`` (who is in the business, with which role) on the business's memberships;

``POST /internal/sessions/revoke`` (``{user_id, hub_id?}``, PLAN-SAAS §2.1) → ``base.session.revoke``, on the same
scope: 200 ``{ended}`` with the sessions of that SaaS account it ended, on that business or, without it, everywhere
(the Hub admin's included); an unknown business ends nothing and answers the same.

The demos (plan 2026-10-17, §1.5 and §1.6), on the same scope:

- ``POST /internal/demos`` (``{session_key, vertical, language}``) → ``base.demo.create``: 202 ``{id, slug, status,
  expires_at, created}`` for a new demo (``requested``: the worker clones its database, and the SaaS waits for
  ``ready`` on ``GET /internal/hubs/{id}``), 200 with the live one of that browser, 503 ``base.demo_full`` with
  ``Retry-After`` when every demo is taken;
- ``POST /internal/demos/{slug}/codes`` (``{session_key, language}``) → ``base.demo.code_create``: 201 ``{code,
  expires_at}``; 404 without such a demo, 410 ``base.hub_gone`` once it ended, 403 ``base.demo_not_owner`` for
  another browser, 503 ``base.hub_preparing`` while it is being made. The path names the demo: v2 binds the signature
  to it.

While the SaaS may still sign v1 only, a body that names the hub of its path (``hub_id`` or ``id``) must name the
same one (422 ``internal.hub_mismatch``).

``/internal/platform/invoices`` (contract point 4, PLAN-SAAS §4) is the door to ERPlora's own hub, which issues
ERPlora's invoices: ``GET …/health`` (200 ``{"status": "ok"}`` or 503 ``{"status": "unconfigured", "detail"}``),
``POST …`` (the body of the SaaS's ``platform_payload()``; 201, or 200 when it was issued before), ``GET …/{id}`` (its
status) and ``GET …/{id}/pdf`` (its PDF, printed after the read, outside any transaction). Each runs its operation of
Invoicing as the system on ``PLATFORM_HUB_SLUG`` and answers ``{"status", "qr", "error"}``.

``/internal/whatsapp/*`` are erplora.com's WhatsApp doors (``apps/whatsapp_inbox/WORKBOOK.md``, «Contrato con el
SaaS», doors 1–3): ``POST …/inbound`` → ``whatsapp_inbox.message.receive`` (200 ``{id, conversation_id, created}``),
``POST …/status`` → ``whatsapp_inbox.message.update_status`` (200 ``{updated, status}``) and ``PUT …/channel`` →
``whatsapp_inbox.channel.sync`` (200 ``{applied, version}``). The body names the business (``hub``: its slug in phase
1), whose host gate answers first (404 ``not_found`` unknown, 410 gone, 503 being prepared, 402 suspended); then the
app off in it is 404 ``app_inactive`` (erplora.com keeps the message and tries again), and the operation runs as the
system on that business, whose refusals (422 out of contract…) are answered with their own envelope.

Their databases (phase 2, S1; plan 2026-10-22): the registry's and the demos' operations run on control
(``base.tenancy.context.operation_database``); the WhatsApp doors enter the business's hub (``use_hub``) before they ask
whether the app is on in it (its rows are in its database: the host erplora.com calls, ``hub.erplora.internal``, opens
no context), and a database that fails them there is 503 ``base.hub_unavailable``, logged; ERPlora's invoices run in
the platform hub's own database (its registry row, made by ``create_platform_hub``; S5).
"""

import json
import logging
from collections.abc import Callable
from functools import wraps
from uuid import UUID

from django.conf import settings
from django.db import DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from live.context import OperationContext, Scope, system_context
from live.errors import OperationError
from live.operations import get as get_operation
from pydantic import ValidationError

from base import registry, relay
from base.registry import REGISTRY_SCOPE
from base.tenancy.context import HubWithoutDatabase, use_hub
from base.tenancy.identity import HubIdentityMismatch
from base.services import DEMO_FULL_RETRY_AFTER_SECONDS, WHATSAPP_APP
from base.throttle import AttemptLimit, RateLimited, client_key

# ``SIGNATURE_V2_HEADER`` and ``sign_v2`` stay importable from here for the apps that sign their own calls to the
# SaaS (``apps/verifactu/representation.py``); they are ``base.signing``'s.
from base.signing import SIGNATURE_V2_HEADER, sign_v2, verify_request  # noqa: F401

logger = logging.getLogger(__name__)

#: The business's commercial status as the photo says it (PLAN-SAAS §2.3).
HUB_STATUSES = ("active", "past_due", "suspended")
#: Calls with a refused signature per caller: 30 within 5 minutes of the first (README, «Límites de intentos»).
SIGNATURE_ATTEMPTS = AttemptLimit("internal", attempts=30, window=300)


def refuse(status: int, code: str, message: str) -> JsonResponse:
    """The error envelope of an internal call (``{"error": {"code", "message"}}``)."""
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def internal_view(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    """A view of ``/internal``: no CSRF (no browser), never cached, and 401 ``internal.unsigned`` unless signed (429
    ``base.rate_limited`` from a caller past :data:`SIGNATURE_ATTEMPTS`)."""

    @wraps(view)
    def guarded(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if not verify_request(request):
            caller = client_key(request)
            wait = SIGNATURE_ATTEMPTS.wait(caller)
            if wait:
                limited = JsonResponse(RateLimited().envelope(), status=429)
                limited["Retry-After"] = str(wait)
                return limited
            SIGNATURE_ATTEMPTS.failed(caller)
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


def _body_object(request: HttpRequest) -> dict | None:
    """The body as a JSON object, or ``None`` when it is none."""
    try:
        body = json.loads(request.body)
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _hub_mismatch() -> JsonResponse:
    return refuse(422, "internal.hub_mismatch", "The body names another hub than its path.")


def _registry_context() -> OperationContext:
    return system_context(REGISTRY_SCOPE)


def _hub_answer(answer) -> dict:
    return answer.model_dump(mode="json", exclude={"created"})


@internal_view
@require_http_methods(["PUT", "GET", "DELETE"])
def hub(request: HttpRequest, hub_id: UUID) -> HttpResponse:
    """``/internal/hubs/{id}``: ``PUT`` registers the business, ``GET`` reads it, ``DELETE`` cancels it."""
    if request.method == "GET":
        answer, refused = _operation_call("base.hub.get", {"id": str(hub_id)}, _registry_context())
        return refused or JsonResponse(_hub_answer(answer))
    body = _body_object(request)
    if body is None:
        return _payload_invalid("The body is not a JSON object.")
    if _names_another_hub(body, hub_id):
        return _hub_mismatch()
    if request.method == "DELETE":
        answer, refused = _operation_call("base.hub.cancel", {"id": str(hub_id)}, _registry_context())
        return refused or JsonResponse(_hub_answer(answer), status=202)
    answer, refused = _operation_call("base.hub.register", {**body, "id": str(hub_id)}, _registry_context())
    if refused is not None:
        return refused
    # 202 while its database is being made (the worker's; the SaaS hears ``ready``), 200 for an update of a ready one.
    return JsonResponse(_hub_answer(answer), status=200 if answer.status == "ready" else 202)


@internal_view
@require_http_methods(["GET"])
def hub_dumps(request: HttpRequest, hub_id: UUID) -> HttpResponse:
    """``GET /internal/hubs/{id}/dumps``: the copies of the business's data, each with a link of 15 minutes."""
    answer, refused = _operation_call("base.hub.dump_list", {"id": str(hub_id)}, _registry_context())
    return refused or JsonResponse(answer.model_dump(mode="json"))


@internal_view
@require_http_methods(["GET"])
def usage(request: HttpRequest) -> HttpResponse:
    """``GET /internal/usage?day=YYYY-MM-DD[&cursor=]``: one page of what the businesses used that day (UTC)."""
    payload = {"day": request.GET.get("day"), "cursor": request.GET.get("cursor") or None}
    answer, refused = _operation_call("base.usage.list", payload, _registry_context())
    return refused or JsonResponse(answer.model_dump(mode="json"))


@internal_view
@require_http_methods(["POST"])
def hub_restore(request: HttpRequest, hub_id: UUID) -> HttpResponse:
    """``POST /internal/hubs/{id}/restore``: bring a cancelled business back; 409 ``hub_purged`` if it is gone."""
    body = _body_object(request)
    if body is None:
        return _payload_invalid("The body is not a JSON object.")
    if _names_another_hub(body, hub_id):
        return _hub_mismatch()
    answer, refused = _operation_call("base.hub.restore", {"id": str(hub_id)}, _registry_context())
    return refused or JsonResponse(_hub_answer(answer))


@internal_view
@require_http_methods(["PUT"])
def hub_state(request: HttpRequest, hub_id: UUID) -> HttpResponse:
    """``PUT /internal/hubs/{id}/state``: the SaaS's photo of a business; an older ``version`` changes nothing."""
    body = _body_object(request)
    if body is None:
        return _payload_invalid("The body is not a JSON object.")
    if _names_another_hub(body, hub_id):
        return _hub_mismatch()
    version = body.get("version")
    if type(version) is not int or version < 0:
        return _payload_invalid("The version is a whole number, zero or more.")
    status = body.get("status")
    if status is not None and status not in HUB_STATUSES:
        return _payload_invalid(f"The status is one of {', '.join(HUB_STATUSES)}.")
    block = body.get("verifactu")
    if block is not None and not isinstance(block, dict):
        return _payload_invalid("The verifactu block is a JSON object.")
    answer, refused = _operation_call(
        "base.hub.state_apply",
        {
            "id": str(hub_id),
            "version": version,
            "status": status,
            "verifactu": block,
            # Not an object: the operation's input refuses it (422).
            "whatsapp": body.get("whatsapp"),
            # Not a list of members: the operation's input refuses it (422).
            "members": body.get("members"),
            "photo": body,
        },
        _registry_context(),
    )
    return refused or JsonResponse({"applied": answer.applied, "version": answer.version})


@internal_view
@require_http_methods(["POST"])
def demos(request: HttpRequest) -> HttpResponse:
    """``POST /internal/demos``: a demo for the SaaS's browser; 202 when it is new (``requested``: the worker makes its
    database and the SaaS waits for ``ready``), 200 when it is its live one."""
    body = _body_object(request)
    if body is None:
        return _payload_invalid("The body is not a JSON object.")
    answer, refused = _operation_call("base.demo.create", body, _registry_context())
    if refused is not None:
        if refused.status_code == 503:
            refused["Retry-After"] = str(DEMO_FULL_RETRY_AFTER_SECONDS)
        return refused
    return JsonResponse(answer.model_dump(mode="json"), status=202 if answer.created else 200)


@internal_view
@require_http_methods(["POST"])
def demo_codes(request: HttpRequest, slug: str) -> HttpResponse:
    """``POST /internal/demos/{slug}/codes``: a one-time code into the demo ``slug`` for the browser that owns it."""
    body = _body_object(request)
    if body is None:
        return _payload_invalid("The body is not a JSON object.")
    answer, refused = _operation_call("base.demo.code_create", {**body, "slug": slug}, _registry_context())
    return refused or JsonResponse(answer.model_dump(mode="json"), status=201)


@internal_view
@require_http_methods(["POST"])
def sessions_revoke(request: HttpRequest) -> HttpResponse:
    """``POST /internal/sessions/revoke`` (``{user_id, hub_id?}``, PLAN-SAAS §2.1): end the Hub's sessions of a SaaS
    account, on one business or everywhere (the Hub admin's included); 200 ``{ended}``, idempotent."""
    body = _body_object(request)
    if body is None:
        return _payload_invalid("The body is not a JSON object.")
    answer, refused = _operation_call("base.session.revoke", body, _registry_context())
    return refused or JsonResponse({"ended": answer.ended})


# ── erplora.com's WhatsApp doors (doors 1–3 of the inbox's contract) ───────────────────────────────────────────────


def _whatsapp_call(request: HttpRequest, name: str) -> HttpResponse:
    """Runs ``name`` as the system on the business the body names (``hub``), once its host opens and the app is on."""
    body = _body_object(request)
    if body is None:
        return _payload_invalid("The body is not a JSON object.")
    slug = body.pop("hub", None)
    if not isinstance(slug, str) or not slug:
        return JsonResponse(
            {
                "error": {
                    "code": "internal.payload_invalid",
                    "message": "The body is out of contract.",
                    "fields": {"hub": "The business's slug is required."},
                }
            },
            status=422,
        )
    hub = registry.hub_by_slug(slug)
    closed = registry.refusal(hub)
    if closed is not None:
        return refuse(closed.status, closed.code, closed.message)
    scope = Scope("host", slug)
    try:
        with use_hub(hub):
            # Which apps are on is the business's (its database): asked inside it, as the photo asks it.
            if WHATSAPP_APP not in relay.active_apps(scope):
                return refuse(404, "app_inactive", "WhatsApp is not on in this business.")
            answer, refused = _operation_call(name, body, system_context(scope))
    except HubIdentityMismatch:
        # Not its own: nothing is served from it and an alarm is raised, as on its host (base.middleware).
        logger.critical(
            "base.hub_unavailable hub=%s: its database is not its own; %s refused.", slug, name, exc_info=True
        )
        return _unavailable()
    except DatabaseError:
        # Unreachable now: erplora.com keeps the message and tries again.
        logger.warning("base.hub_unreachable hub=%s: %s could not reach its database now.", slug, name, exc_info=True)
        return _unavailable()
    return refused or JsonResponse(answer.model_dump(mode="json"))


def _unavailable() -> JsonResponse:
    unavailable = registry.unavailable()
    return refuse(unavailable.status, unavailable.code, unavailable.message)


@internal_view
@require_http_methods(["POST"])
def whatsapp_inbound(request: HttpRequest) -> HttpResponse:
    """``POST /internal/whatsapp/inbound``: a customer's message, or the owner's reply from the phone; once per id."""
    return _whatsapp_call(request, "whatsapp_inbox.message.receive")


@internal_view
@require_http_methods(["POST"])
def whatsapp_status(request: HttpRequest) -> HttpResponse:
    """``POST /internal/whatsapp/status``: Meta's status of a message the business sent."""
    return _whatsapp_call(request, "whatsapp_inbox.message.update_status")


@internal_view
@require_http_methods(["PUT"])
def whatsapp_channel(request: HttpRequest) -> HttpResponse:
    """``PUT /internal/whatsapp/channel``: the number's state, its month and its templates; an older version is ignored."""
    return _whatsapp_call(request, "whatsapp_inbox.channel.sync")


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
    """Runs ``name`` as the system on the platform hub, in its own database: its output, or the response of its
    refusal.

    The platform hub is the registry's row of ``PLATFORM_HUB_SLUG`` with a database of its own, as any business since
    S5 (``manage.py create_platform_hub --execute`` makes both): without it, 503 ``base.platform_hub_missing``, saying
    so; a database that is not its own or cannot be reached now, 503 as for any business."""
    hub = registry.hub_by_slug(settings.PLATFORM_HUB_SLUG)
    if hub is None or registry.refusal(hub) is not None:
        return None, refuse(
            503,
            "base.platform_hub_missing",
            "ERPlora's platform hub has no database of its own yet: run manage.py create_platform_hub --execute.",
        )
    try:
        with use_hub(hub):
            return _operation_call(name, payload, _platform_context())
    except HubIdentityMismatch:
        logger.critical("base.hub_unavailable hub=%s: its database is not its own; %s refused.", hub.slug, name)
        return None, _unavailable()
    except (DatabaseError, HubWithoutDatabase):
        logger.warning("base.hub_unreachable hub=%s: %s could not reach its database now.", hub.slug, name)
        return None, _unavailable()


def _operation_call(name: str, payload: dict, ctx: OperationContext):
    """Runs the operation ``name`` with ``payload`` in ``ctx``: ``(output, None)``, or ``(None, the refusal)``."""
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
        return op(ctx, data), None
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
