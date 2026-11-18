"""«Report a problem» (``base.support.report``) and the pass to erplora.com (``base.saas_pass.create``).

The user menu's dialog sends it to erplora.com, which mails its support mailbox «Reply-To» the account and limits it
per account (SUPPORT_REPORT_RATELIMIT, the panel's and the hub's together): the hub keeps nothing and limits nothing.

«Upgrade plan» and «erplora.com» arrive already signed in. The Hub signs and the SaaS only checks, so nothing asks the
SaaS anything per request. It is signed at the click, never in the shell's HTML: it would expire in a
minute and every script of the page could read it. The pass opens a session, so it is never logged.
"""

import json
import logging
import secrets
import time
from urllib.parse import urlencode

from django.conf import settings
from django.core import signing as django_signing
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import InvalidPayload, OperationError, PermissionDenied
from live.operations import AI, INTERNAL, operation

from base import auth, signing
from base.access import CREDENTIAL_SESSION_KEY
from base.models import SessionOwner
from base.permissions import OPEN_MANAGEMENT, VIEW_HOME
from base.schemas import SaasPassIn, SaasPassOut, SupportReportIn, SupportReportOut
from base.services.devices import saas_user_id_of
from base.services.sessions import SAAS_USERNAME_PREFIX

logger = logging.getLogger(__name__)


SUPPORT_REPORT_PATH = "/internal/support/report"
#: Characters of the browser a report sends: erplora.com keeps as many.
REPORT_BROWSER_MAX = 300


def _session_account(ctx: OperationContext) -> str | None:
    """The erplora.com account behind this session: only a session opened with it on this hub. A PIN or a badge on a
    shared till, a demo's visitor or a call without a session has none, and neither has a session that
    does not say how it was opened (``CREDENTIAL_SESSION_KEY``): never the account by default."""
    request, user = ctx.request, ctx.actor
    username = user.get_username() if hasattr(user, "get_username") else ""
    opened_with = request.session.get(CREDENTIAL_SESSION_KEY) if request is not None else None
    if (
        not username.startswith(SAAS_USERNAME_PREFIX)
        or opened_with != SessionOwner.Credential.ACCOUNT
        or getattr(request, "hub", None) is None
    ):
        return None
    return saas_user_id_of(user)


def _reporting_account(ctx: OperationContext) -> str:
    """The account support answers to (``_session_account``), or the refusal that says how to report."""
    account = _session_account(ctx)
    if account is None:
        raise PermissionDenied(
            gettext("Sign in with your erplora.com account to report a problem."), code="base.support_needs_account"
        )
    return account


def _report_not_sent() -> OperationError:
    return OperationError(
        gettext("We could not send your report. Write to us directly at %(email)s.") % {"email": settings.SUPPORT_EMAIL},
        code="base.report_not_sent",
        status=503,
    )


def _reply_to(answer: bytes) -> str | None:
    """The address erplora.com says support answers to, or ``None`` when its answer is no report sent."""
    try:
        payload = json.loads(answer)
    except ValueError:
        return None
    reply_to = payload.get("reply_to") if isinstance(payload, dict) else None
    return reply_to if isinstance(reply_to, str) and reply_to else None


@operation(
    "base.support.report",
    kind="command",
    permission=VIEW_HOME,
    input=SupportReportIn,
    output=SupportReportOut,
    ai=AI(
        description=(
            "Sends erplora.com's support team a problem the person describes: a short subject and what happened. Their "
            "account, this business, the screen and the browser go with it, and support answers by email to their "
            "account. Only for a person who entered with their erplora.com account, never with a PIN."
        ),
        asks={
            "en": (
                "tell support the payment screen freezes",
                "report a bug: the totals don't add up",
                "send ERPlora a problem",
            ),
            "es": (
                "reporta un fallo: no me cuadran los totales",
                "mándale una incidencia a ERPlora",
                "avisa a soporte de que la app se queda colgada",
            ),
        },
    ),
    # It waits on erplora.com: no transaction holds the hub's connection meanwhile.
    database=False,
)
def support_report(ctx: OperationContext, data: SupportReportIn) -> dict:
    """«Report a problem» (BASE-F108): ``POST {SAAS_INTERNAL_URL}/internal/support/report``, signed v1 + v2, with the
    account, the business, the screen and the browser. erplora.com's limit is «Too many attempts…»; erplora.com out of
    reach or refusing it, the address to write to. The text is never logged."""
    account = _reporting_account(ctx)
    subject, description = data.subject.strip(), data.description.strip()
    missing = {}
    if not subject:
        missing["subject"] = gettext("Add a subject.")
    if not description:
        missing["description"] = gettext("Describe the problem, please.")
    if missing:
        raise InvalidPayload(" ".join(missing.values()), code="base.support_report_incomplete", fields=missing)
    request = ctx.request
    hub = request.hub
    body = json.dumps(
        {
            "account": account,
            "hub": hub.slug,
            "hub_id": str(hub.id),
            "page": data.page,
            "browser": request.headers.get("User-Agent", "")[:REPORT_BROWSER_MAX],
            "subject": subject,
            "description": description,
        }
    ).encode()
    headers = {
        "Content-Type": "application/json",
        **signing.signed_headers("POST", SUPPORT_REPORT_PATH, body, int(time.time()), settings.INTERNAL_SHARED_SECRET),
    }
    try:
        status, answer = auth.post(auth.saas_internal_url(SUPPORT_REPORT_PATH), body, headers, auth.TIMEOUT_SECONDS)
    except OSError as failed:
        logger.warning("base.support_report_not_sent hub=%s: the SaaS is unreachable (%s).", hub.slug, failed)
        raise _report_not_sent() from None
    if status == 429:
        raise OperationError(
            gettext("Too many attempts. Please try again in a few minutes."), code="base.too_many_attempts", status=429
        )
    reply_to = _reply_to(answer) if status == 200 else None
    if reply_to is None:
        logger.warning("base.support_report_not_sent hub=%s: the SaaS answered %s.", hub.slug, status)
        raise _report_not_sent()
    logger.info("base.support_report_sent hub=%s", hub.slug)
    return {"reply_to": reply_to}




#: erplora.com's door and its salt: a value signed for anything else with the same secret is no pass.
SAAS_PASS_PATH = "/hub-pass/"
SAAS_PASS_SALT = "erplora.hub-pass.v1"


@operation(
    "base.saas_pass.create",
    kind="command",
    permission=VIEW_HOME,
    input=SaasPassIn,
    output=SaasPassOut,
    # A pass in a chat would stay in its history and in the model's context for a minute.
    ai=INTERNAL,
    database=False,
)
def saas_pass_create(ctx: OperationContext, data: SaasPassIn) -> dict:
    """The address of erplora.com with a pass of this person to this business's plan or panel: a minute, one use. The
    SaaS decides again whether the account is a member; ``business`` here only for who may see that button."""
    account = _session_account(ctx)
    if account is None:
        raise PermissionDenied(
            gettext("Sign in with your erplora.com account to go there directly."), code="base.saas_pass_needs_account"
        )
    if data.next == "business" and not ctx.has(OPEN_MANAGEMENT):
        raise PermissionDenied(
            gettext("You don't have permission to manage this business on erplora.com."),
            code="base.saas_pass_needs_management",
        )
    secret = settings.INTERNAL_SHARED_SECRET
    if not secret:
        # Django's signer would fall back on SECRET_KEY, and erplora.com would refuse that pass.
        logger.error("base.saas_pass_unavailable hub=%s: INTERNAL_SHARED_SECRET is empty.", ctx.request.hub.slug)
        raise OperationError(
            gettext("We could not open erplora.com directly."), code="base.saas_pass_unavailable", status=503
        )
    token = django_signing.dumps(
        {"user": account, "hub": ctx.request.hub.slug, "next": data.next, "nonce": secrets.token_urlsafe(32)},
        key=secret,
        salt=SAAS_PASS_SALT,
    )
    return {"url": auth.saas_url(f"{SAAS_PASS_PATH}?{urlencode({'pass': token})}")}
