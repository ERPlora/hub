"""The business's number: the photo erplora.com pushes of the channel and its templates (WHATSAPP_INBOX-F27,
F28), and connecting or disconnecting the number from Settings through erplora.com's doors 10–12 (F01, F02)."""

import logging
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, OperationError
from live.operations import atomic, operation
from live.outbox import record_event

from apps.whatsapp_inbox import clock, events, gateway
from apps.whatsapp_inbox.models import Channel, Template
from apps.whatsapp_inbox.queries.reasons import META_RATE_LIMITED
from apps.whatsapp_inbox.queries.templates import live_templates, templates_of
from apps.whatsapp_inbox.schemas.channel import (
    ChannelConnectIn,
    ChannelConnectOut,
    ChannelDisconnectIn,
    ChannelDisconnectOut,
    ChannelPrepareIn,
    ChannelPrepareOut,
    ChannelSyncIn,
    ChannelSyncOut,
)

from .writes import RECEIVE

logger = logging.getLogger(__name__)


@operation(
    "whatsapp_inbox.channel.sync",
    kind="command",
    permission=RECEIVE,
    input=ChannelSyncIn,
    output=ChannelSyncOut,
    ai={
        "description": "System only (erplora.com's /internal/whatsapp/channel and the state snapshot): the "
        "number's state, the month's allowance and spend, and the templates Meta holds; an older version is ignored.",
        "risk": "normal",
    },
)
def sync_channel(ctx: OperationContext, data: ChannelSyncIn) -> dict:
    row = _locked_channel(ctx)
    if data.version <= row.version:
        return {"applied": False, "version": row.version}
    now = clock.now()
    row.version = data.version
    row.status = data.status
    row.phone_number = data.phone_number
    row.display_name = data.display_name
    row.monthly_limit = data.monthly_limit
    row.monthly_usage = data.monthly_usage
    row.usage_month = data.usage_month
    row.synced_at = now
    row.save()
    if data.templates is not None:
        _sync_templates(ctx, data.templates, now)
    record_event(ctx, events.CHANNEL_SYNCED, {"version": data.version})
    return {"applied": True, "version": data.version}


def _locked_channel(ctx: OperationContext) -> Channel:
    """The row of the business of ``ctx``, locked; born the first time erplora.com speaks of it (two at once: one
    creates it, the other finds it)."""
    rows = Channel.objects.select_for_update()
    row = rows.first()
    if row is None:
        try:
            with atomic():
                row = Channel.objects.create()
        except IntegrityError:
            row = rows.get()
    return row


def _sync_templates(ctx: OperationContext, items, now) -> None:
    """Meta's list replaces the copy (F27, F28): what it no longer lists is «Deleted in WhatsApp Manager».

    Never on what the Hub has not handed over yet (a new template on its way or not accepted keeps what was
    written; an edit waits in its ``draft``), and never bringing back a template deleted here: Meta still
    lists it until the deletion reaches it, or by the same id. Only the business's own templates: another
    business's list never touches them.
    """
    kept = []
    for item in items:
        row = live_templates(ctx.scope).select_for_update().filter(name=item.name, language=item.language).first()
        if row is None:
            deleted = templates_of(ctx.scope).filter(name=item.name, language=item.language, deleted_at__isnull=False)
            if deleted.filter(Q(delete_state=Template.DeleteState.PENDING) | Q(meta_id=item.meta_id)).exists():
                continue
            row = Template(name=item.name, language=item.language)
        elif row.status == Template.Status.DRAFT and row.submit_state:
            kept.append(row.pk)
            continue
        row.category = item.category
        row.status = item.status
        header_format = item.header_format if item.header_format is not None else ("TEXT" if item.header else "")
        if header_format != row.header_format:
            row.header_sample = None  # changed in WhatsApp Manager: the file chosen here is no longer its header
        row.header_format = header_format
        row.header = item.header
        row.body = item.body
        row.body_examples = list(item.body_examples)
        row.footer = item.footer
        row.buttons = list(item.buttons)
        row.variables = item.variables
        row.rejected_reason = item.rejected_reason
        row.meta_id = item.meta_id
        row.synced_at = now
        row.save()
        kept.append(row.pk)
    live_templates(ctx.scope).exclude(pk__in=kept).exclude(
        status__in=[Template.Status.DELETED, Template.Status.DRAFT]
    ).update(status=Template.Status.DELETED, synced_at=now)


# Commands, the three of them, although ``prepare`` writes nothing: a query opens its READ ONLY transaction before
# its first line, and nothing waits for erplora.com inside a transaction. Each asks erplora.com first, before any
# read or write of its own, so no transaction is open while it answers; then ``connect`` and ``disconnect`` keep
# erplora.com's answer in the business's row at once (its photo, pushed meanwhile, says the same with a newer version,
# and the next one still wins).

CONFIGURE = "whatsapp_inbox.configure"
#: The COOP values that keep the window a page opens (Django's default, ``same-origin``, cuts it: Meta's window
#: could never tell this page how it ended).
KEEPS_POPUPS = frozenset({"same-origin-allow-popups", "unsafe-none"})
GRAPH_VERSION = re.compile(r"^v\d{1,3}\.\d{1,3}$")
META_ID = re.compile(r"^\d{1,50}$")
E164 = re.compile(r"^\+[1-9]\d{6,14}$")

CONNECT_UNCONFIGURED = _("This server is not linked to erplora.com: the number cannot be connected from it.")
CONNECT_SAAS_UNREACHABLE = _("Your hub could not reach erplora.com. Check the connection and try again.")
CONNECT_UNKNOWN = _(
    "erplora.com did not confirm the connection. In a moment «Your number» will say whether it is connected; "
    "if it is not, connect it again."
)
DISCONNECT_UNKNOWN = _(
    "erplora.com did not confirm the disconnection. In a moment «Your number» will say it; if it is still "
    "connected, try again."
)
HUB_UNKNOWN = _("erplora.com does not know this business: a demo cannot connect a WhatsApp number.")
CONNECT_REJECTED = _("Meta did not accept the connection: %(reason)s")
NUMBER_NOT_IN_ACCOUNT = _(
    "The number chosen in Meta's window is not in that WhatsApp Business account: nothing was connected."
)
NUMBER_NOT_CHOSEN = _("That WhatsApp Business account has several numbers: choose one in Meta's window.")
CONNECT_META_UNREACHABLE = _("Meta did not answer: nothing was connected. Try again.")
WHATSAPP_UNAVAILABLE = _("WhatsApp is not available in ERPlora yet.")
SAAS_REFUSED = _("erplora.com did not take the request (%(code)s). Try again later.")

#: erplora.com's refusal at doors 10–12 → (status, the Hub's code, its message). A message with ``%(reason)s``
#: carries erplora.com's (Meta's) own words.
DOOR_REFUSALS = {
    "hub_unknown": (409, "whatsapp_inbox.hub_unknown", HUB_UNKNOWN),
    "whatsapp.meta_rejected": (409, "whatsapp_inbox.meta_rejected", CONNECT_REJECTED),
    "whatsapp.number_not_in_account": (409, "whatsapp_inbox.number_not_in_account", NUMBER_NOT_IN_ACCOUNT),
    "whatsapp.number_not_chosen": (409, "whatsapp_inbox.number_not_chosen", NUMBER_NOT_CHOSEN),
    "whatsapp.meta_rate_limited": (409, "whatsapp_inbox.meta_rate_limited", META_RATE_LIMITED),
    "whatsapp.meta_unreachable": (503, "whatsapp_inbox.meta_unreachable", CONNECT_META_UNREACHABLE),
    "whatsapp.meta_no_token": (503, "whatsapp_inbox.meta_unreachable", CONNECT_META_UNREACHABLE),
    "whatsapp.not_configured": (409, "whatsapp_inbox.whatsapp_unavailable", WHATSAPP_UNAVAILABLE),
}


def _ask_saas(door, unknown=None, **args) -> dict:
    """erplora.com's 200 body at ``door``, or the refusal the screen shows. ``unknown``: the message when the request
    left and no answer came back (by default, as nothing left)."""
    try:
        reply = door(**args)
    except gateway.NotConfigured:
        raise Conflict(str(CONNECT_UNCONFIGURED), code="whatsapp_inbox.saas_unconfigured") from None
    if reply.kind == gateway.ACCEPTED:
        return reply.data
    if reply.kind == gateway.REFUSED:
        status, code, message = DOOR_REFUSALS.get(reply.code, (503, "whatsapp_inbox.saas_refused", SAAS_REFUSED))
        if code == "whatsapp_inbox.saas_refused":
            logger.error("whatsapp_inbox.door.refused status=%s code=%s", reply.http_status, reply.code)
        text = str(message) % {"reason": reply.message or "—", "code": reply.code}
        raise OperationError(text, code=code, status=status)
    logger.warning("whatsapp_inbox.door.%s %s", reply.kind, reply.message)
    if reply.kind == gateway.UNKNOWN and unknown is not None:
        raise OperationError(str(unknown[1]), code=unknown[0], status=503)
    raise OperationError(str(CONNECT_SAAS_UNREACHABLE), code="whatsapp_inbox.saas_unreachable", status=503)


def _not_understood(door: str) -> OperationError:
    logger.error("whatsapp_inbox.door.not_understood door=%s", door)
    return OperationError(str(CONNECT_SAAS_UNREACHABLE), code="whatsapp_inbox.saas_unreachable", status=503)


def _return_page(value) -> str:
    """erplora.com's page Meta brings the code back to: an address of erplora.com's own origin (the one the Hub
    knows, ``SAAS_URL``: same scheme, host and port) without a fragment, or ``""``. Over https; plain http only in
    development (``DEBUG``) with an http ``SAAS_URL``, as erplora.com's own rule (``whatsapp.meta.redirect_uri``)."""
    if not isinstance(value, str) or not value:
        return ""
    try:
        page, known = urlsplit(value), urlsplit(str(getattr(settings, "SAAS_URL", "") or ""))
    except ValueError:
        # An address that cannot be read (an unclosed IPv6 bracket) is no page to bring the code back to.
        return ""
    schemes = ("https", "http") if settings.DEBUG else ("https",)
    if page.scheme not in schemes or not page.netloc or page.fragment or (page.scheme, page.netloc) != (known.scheme, known.netloc):
        return ""
    return value


@operation(
    "whatsapp_inbox.channel.prepare",
    kind="command",
    permission=CONFIGURE,
    input=ChannelPrepareIn,
    output=ChannelPrepareOut,
    ai={
        "asks": {
            "en": (
                "can I connect WhatsApp yet?",
                "what's missing to connect our WhatsApp number?",
                "is WhatsApp ready to connect from Settings?",
            ),
            "es": (
                "¿se puede preparar ya la conexión de WhatsApp?",
                "¿qué me falta para conectar el número de WhatsApp?",
                "¿está todo preparado para conectar WhatsApp en Ajustes?",
            ),
        },
        "description": "Whether the business's WhatsApp number can be connected from Settings now (Meta's window "
        "opens there, and only a person in it connects a number), and why not: WhatsApp not set up on erplora.com "
        "yet, or the window not available yet.",
        "risk": "normal",
    },
)
def prepare_connect(ctx: OperationContext, data: ChannelPrepareIn) -> dict:
    """What Settings opens Meta's window with (erplora.com's door 10), and why it cannot be opened yet."""
    answer = _ask_saas(gateway.config, hub=ctx.scope.key)
    if not isinstance(answer.get("configured"), bool):
        raise _not_understood("config")
    if not answer["configured"]:
        return {"available": False, "reason": "not_configured"}
    ids = {key: answer.get(key) for key in ("app_id", "config_id", "graph_version")}
    if not all(isinstance(value, str) for value in ids.values()) or not (
        META_ID.match(ids["app_id"]) and META_ID.match(ids["config_id"]) and GRAPH_VERSION.match(ids["graph_version"])
    ):
        raise _not_understood("config")
    redirect_uri = _return_page(answer.get("redirect_uri"))
    if not redirect_uri:
        return {"available": False, "reason": "window_unavailable", **ids}
    if getattr(settings, "SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin") not in KEEPS_POPUPS | {None}:
        return {"available": False, "reason": "popups_blocked", **ids}
    return {"available": True, "reason": None, **ids, "redirect_uri": redirect_uri}


@operation(
    "whatsapp_inbox.channel.connect",
    kind="command",
    permission=CONFIGURE,
    input=ChannelConnectIn,
    output=ChannelConnectOut,
    ai={
        "asks": {
            "en": (
                "connect our WhatsApp number with the code from Meta",
                "finish connecting WhatsApp, here is the code",
                "link the business's WhatsApp with this one-time code",
            ),
            "es": (
                "quiero conectar el WhatsApp del negocio: aquí tienes el código",
                "termina de conectar el número con este código de Meta",
                "enlaza nuestro WhatsApp con el código de un solo uso",
            ),
        },
        "description": "Connect the business's WhatsApp number chosen in Meta's window, with the one-time code that "
        "window returned (it lasts 30 seconds). Only Meta's window in Settings gives that code: to connect a "
        "number, ask the person to press «Connect WhatsApp» in Settings.",
        "risk": "high",
    },
)
def connect_number(ctx: OperationContext, data: ChannelConnectIn) -> dict:
    """Connect the number Meta's window chose (erplora.com's door 11), with what the window gave, as it came; the
    business's row says it at once."""
    answer = _ask_saas(
        gateway.connect, unknown=("whatsapp_inbox.connect_unknown", CONNECT_UNKNOWN), hub=ctx.scope.key, **data.model_dump()
    )
    out = _connected(answer)
    if out is None:
        logger.error("whatsapp_inbox.door.not_understood door=connect")
        raise OperationError(str(CONNECT_UNKNOWN), code="whatsapp_inbox.connect_unknown", status=503)
    row = _locked_channel(ctx)
    row.status = Channel.Status.CONNECTED
    row.phone_number, row.display_name = out.phone_number, out.display_name
    row.save(update_fields=["status", "phone_number", "display_name", "updated_at"])
    record_event(ctx, events.CHANNEL_CONNECTED, {"history_requested": out.history_requested})
    return out


def _connected(answer: dict) -> ChannelConnectOut | None:
    """Door 11's 200 as the Hub keeps it: connected, an E.164 number and WhatsApp's name; anything else, ``None``."""
    try:
        out = ChannelConnectOut.model_validate(answer)
    except ValueError:
        return None
    if answer.get("connected") is not True or not E164.match(out.phone_number) or len(out.display_name) > 200:
        return None
    return out


@operation(
    "whatsapp_inbox.channel.disconnect",
    kind="command",
    permission=CONFIGURE,
    input=ChannelDisconnectIn,
    output=ChannelDisconnectOut,
    ai={
        "asks": {
            "en": (
                "disconnect our WhatsApp number",
                "stop using WhatsApp in the Hub for now",
                "unlink the business's WhatsApp but keep the chats",
            ),
            "es": (
                "desconecta el WhatsApp del negocio",
                "deja de usar nuestro número de WhatsApp por ahora",
                "quita la conexión de WhatsApp sin perder los chats",
            ),
        },
        "description": "Disconnect the business's WhatsApp number (erplora.com stops using it): the inbox no longer "
        "receives nor sends until it is connected again from Settings; the conversations kept stay.",
        "risk": "high",
    },
)
def disconnect_number(ctx: OperationContext, data: ChannelDisconnectIn) -> dict:
    """Disconnect the business's number (erplora.com's door 12). Its answer, whether there was a number or not,
    leaves the business without one at once; the month's figures and the conversations stay."""
    answer = _ask_saas(gateway.disconnect, unknown=("whatsapp_inbox.disconnect_unknown", DISCONNECT_UNKNOWN), hub=ctx.scope.key)
    if not isinstance(answer.get("disconnected"), bool):
        logger.error("whatsapp_inbox.door.not_understood door=disconnect")
        raise OperationError(str(DISCONNECT_UNKNOWN), code="whatsapp_inbox.disconnect_unknown", status=503)
    row = _locked_channel(ctx)
    if row.status != Channel.Status.NOT_CONNECTED or row.phone_number or row.display_name:
        row.status = Channel.Status.NOT_CONNECTED
        row.phone_number = row.display_name = ""
        row.save(update_fields=["status", "phone_number", "display_name", "updated_at"])
        record_event(ctx, events.CHANNEL_DISCONNECTED, {})
    return {"disconnected": answer["disconnected"]}
