"""``/internal/whatsapp/*`` are erplora.com's WhatsApp doors (``apps/whatsapp_inbox/WORKBOOK.md``, «Contrato con el
SaaS», doors 1–3), signed as the rest of ``/internal`` (``base.internal``): ``POST …/inbound`` →
``whatsapp_inbox.message.receive`` (200 ``{id, conversation_id, created}``), ``POST …/status`` → ``whatsapp_inbox.message.update_status`` (200 ``{updated, status}``) and ``PUT …/channel`` →
``whatsapp_inbox.channel.sync`` (200 ``{applied, version}``). The body names the business (``hub``: its slug), whose
host gate answers first (404 ``not_found`` unknown, 410 gone, 503 being prepared, 402 suspended); then the
app off in it is 404 ``app_inactive`` (erplora.com keeps the message and tries again), and the operation runs as the
system on that business, whose refusals (422 out of contract…) are answered with their own envelope.

They enter the business's hub (``use_hub``) before they ask whether the app is on in it (its rows are in its database:
the host erplora.com calls, ``hub.erplora.internal``, opens no context), and a database that fails them there is 503
``base.hub_unavailable``, logged.
"""

import logging

from django.db import DatabaseError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from live.context import Scope, system_context

from base import apps_on, registry, services
from base.internal import _body_object, _operation_call, _payload_invalid, _unavailable, internal_view, refuse
from base.tenancy.context import use_hub
from base.tenancy.identity import HubIdentityMismatch

# Every door of /internal logs as one: the alarms and the tests read ``base.internal``.
logger = logging.getLogger("base.internal")


def _whatsapp_call(request: HttpRequest, name: str) -> HttpResponse:  # noqa: PLR0911
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
            if services.photo.WHATSAPP_APP not in apps_on.active_apps(scope):
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
