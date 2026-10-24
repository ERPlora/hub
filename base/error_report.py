"""``POST /api/error-report``: the errors the screen reports by itself (BASE-G95, G13, G50; the old hub's
``frontend_error_report``, HUB_SHELL-F149).

PLAN-SAAS §1.1 (round 2026-10-15b; PLAN-HUB «Embudo de errores»): a report is one structured line in the log, at
``ERROR``, which CloudWatch counts and alarms on; no table, no issue and no forwarding to erplora.com (each project logs
its own). The SPA sends it with ``navigator.sendBeacon`` (``base/frontend/lib/error-report.ts``), which cannot carry
the CSRF header: the route is exempt because it only writes that line, never data. Only a session of the hub's host is
heard, at most :data:`LIMIT` reports per person and host a minute (the SPA already sends an error once every 30 s);
every field is cut to its length and anything else is dropped, so a report never floods the log nor carries what it
was not asked for. Not a ninja route: a log line is no operation of the business (``config/urls.py`` puts it before the
API's prefix).
"""

import json
import logging
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.translation import gettext
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from base import throttle

logger = logging.getLogger(__name__)

#: The largest report read: an error's message and its stack fit well within it.
MAX_BODY = 16 * 1024
MESSAGE_LENGTH = 1000
STACK_LENGTH = 8000
#: The fields kept besides the message and the stack, each with its longest length.
FIELDS = {"url": 500, "component": 200}
#: What the SPA saw: an error nobody caught, a promise rejected unhandled, or a component that failed to render.
KINDS = frozenset({"error", "unhandledrejection", "vue"})
USER_AGENT_LENGTH = 300
#: Reports a person may send on a host within :data:`WINDOW` seconds.
LIMIT = 30
WINDOW = 60


def _refusal(status: int, code: str, message: str) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


@csrf_exempt
@require_POST
def error_report(request: HttpRequest) -> HttpResponse:
    """Log the report of the screen as one line and answer 204; refuse what is not a session's readable report."""
    if not request.user.is_authenticated:
        return _refusal(401, "unauthorized", gettext("Sign in to report an error."))
    if len(request.body) > MAX_BODY:
        return _refusal(413, "payload_too_large", gettext("The report is too large."))
    report = _read(request.body)
    if report is None:
        return _refusal(400, "invalid_payload", gettext("The report cannot be read."))
    hub = getattr(request, "hub", None)
    host = hub.slug if hub is not None else request.get_host().split(".", 1)[0]
    if not throttle.allow(f"error_report:{host}:{request.user.pk}", limit=LIMIT, window=WINDOW):
        return _refusal(429, "base.rate_limited", gettext("Too many reports for now."))
    line = {
        **report,
        "hub": host,
        "user": str(request.user.pk),
        "user_agent": request.headers.get("User-Agent", "")[:USER_AGENT_LENGTH],
    }
    logger.error("frontend.error %s", json.dumps(line, ensure_ascii=False, separators=(",", ":")))
    return HttpResponse(status=204)


def _read(body: bytes) -> dict[str, Any] | None:
    """The report's fields, each cut to its length; ``None`` when it is no JSON object with a kind and a message."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        return None
    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    report = {"kind": kind, "message": message[:MESSAGE_LENGTH]}
    stack = data.get("stack")
    report["stack"] = stack[:STACK_LENGTH] if isinstance(stack, str) else ""
    for field, length in FIELDS.items():
        value = data.get(field)
        report[field] = value[:length] if isinstance(value, str) else ""
    return report
