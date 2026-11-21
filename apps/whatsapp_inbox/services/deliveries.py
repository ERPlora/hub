"""Handing a message to erplora.com outside any transaction: the claim, the HTTP call and its answer,
and the worker's pass that hands over again what a crash or a stopping worker left half-way."""

import datetime as dt
from uuid import UUID

from live.context import OperationContext, Scope, system_context
from live.operations import get, operation
from live.outbox import record_event

from apps.whatsapp_inbox import clock, events, gateway
from apps.whatsapp_inbox.models import Conversation, Message, Template, TemplateSample
from apps.whatsapp_inbox.queries import (
    HEADER_SAMPLE_MISSING_CODE,
    SAAS_UNREACHABLE_CODE,
    SEND_REFUSED_CODE,
    SEND_UNKNOWN_CODE,
)
from apps.whatsapp_inbox.schemas import ClaimDeliveryOut, MessageRefIn, RecordDeliveryIn, RecordOut, ResumeIn, ResumeOut
from base import outbound

from .erasing import forget
from .template_handover import _TEMPLATE_ON_ITS_WAY, _with_its_file, remove_template, submit_template
from .writes import RECEIVE, _after_commit

#: How long a delivery may be on its way before the worker hands it over again (gateway: 5 + 15 s).
STUCK_AFTER = dt.timedelta(minutes=2)
#: How many deliveries one pass of the worker takes per hub.
RESUME_BATCH = 50

_ON_ITS_WAY = (Message.Status.QUEUED, Message.Status.SENDING)

#: erplora.com's 409 codes the Hub knows by name → its code, said in its own words when read (queries); any other
#: is «erplora.com did not send it», with Meta's reason as it came.
_REFUSALS = {
    "whatsapp.cap_reached": "whatsapp_inbox.cap_reached",
    "whatsapp.not_connected": "whatsapp_inbox.channel_not_connected",
    "whatsapp.reconnect_needed": "whatsapp_inbox.reconnect_needed",
    HEADER_SAMPLE_MISSING_CODE: HEADER_SAMPLE_MISSING_CODE,
}


def deliver(scope: Scope, message_id: UUID) -> None:
    """Hand a queued message to erplora.com (WORKBOOK «Contrato con el SaaS», door 5), with no
    transaction and no lock around the HTTP call; its answer is recorded in a transaction of its own."""
    system = system_context(scope)
    claim = get("whatsapp_inbox.message.claim_delivery")
    claimed = claim(system, MessageRefIn(id=message_id))
    if not claimed.claimed:
        return
    outbound.release()  # erplora.com is waited for with no connection held
    template, reply = _with_its_file(claimed.template) if claimed.template is not None else (None, None)
    if reply is None:
        try:
            reply = gateway.send(
                hub=scope.key,
                to=claimed.to,
                idempotency_key=str(claimed.client_message_id),
                text=claimed.text,
                template=template,
            )
        except gateway.NotConfigured:
            reply = gateway.Reply(
                kind=gateway.UNREACHABLE, message="SAAS_INTERNAL_URL is not set."
            )
    record = get("whatsapp_inbox.message.record_delivery")
    record(
        system,
        RecordDeliveryIn(
            id=message_id,
            kind=reply.kind,
            wa_message_id=reply.wa_message_id,
            code=reply.code,
            message=reply.message,
        ),
    )


@operation(
    "whatsapp_inbox.message.claim_delivery",
    kind="command",
    permission=RECEIVE,
    input=MessageRefIn,
    output=ClaimDeliveryOut,
    ai={
        "description": "System only: takes a queued message to hand it to erplora.com (nobody else is on it), "
        "marking it as sending.",
        "risk": "normal",
    },
)
def claim_delivery(ctx: OperationContext, data: MessageRefIn) -> dict:
    message = (
        Message.objects.select_for_update(of=("self",), skip_locked=True)
        .select_related("conversation")
        .filter(pk=data.id, origin=Message.Origin.HUB, status__in=_ON_ITS_WAY)
        .first()
    )
    if message is None:
        return {"claimed": False}
    if message.conversation.erased_at is not None:
        message.status = Message.Status.FAILED
        message.error_code = "whatsapp_inbox.conversation_erased"
        message.error_message = ""
        message.save(update_fields=["status", "error_code", "error_message"])
        return {"claimed": False}
    message.status = Message.Status.SENDING
    message.status_at = clock.now()
    message.save(update_fields=["status", "status_at"])
    template = (
        {
            "name": message.template_name,
            "language": message.template_language,
            "variables": message.template_variables,
        }
        if message.kind == "template"
        else None
    )
    if template is not None and message.header_sample_id is not None:
        # Read after the claim's COMMIT, with no connection held (``deliver``): only a file of its own business.
        sample = TemplateSample.objects.filter(pk=message.header_sample_id).first()
        if sample is not None:
            template.update(header_format=sample.header_format, sample_key=sample.key, sample_name=sample.name)
        else:
            template.update(sample_key="", sample_name="")
    return {
        "claimed": True,
        "to": message.conversation.phone,
        "text": message.body if template is None else None,
        "template": template,
        "client_message_id": message.client_message_id,
    }


@operation(
    "whatsapp_inbox.message.record_delivery",
    kind="command",
    permission=RECEIVE,
    input=RecordDeliveryIn,
    output=RecordOut,
    ai={
        "description": "System only: records erplora.com's answer to a send: sent with Meta's id, refused with "
        "its reason, or still sending (no answer) to retry with the same key.",
        "risk": "normal",
    },
)
def record_delivery(ctx: OperationContext, data: RecordDeliveryIn) -> dict:
    message = Message.objects.select_for_update().filter(pk=data.id).first()
    if message is None:
        return {"status": None}
    on_its_way = message.status in _ON_ITS_WAY
    if data.kind == gateway.SENT:
        if not message.wa_message_id:
            message.wa_message_id = data.wa_message_id
        if on_its_way:
            message.status = Message.Status.SENT
            message.error_code = message.error_message = ""
    elif not on_its_way:
        return {"status": message.status}  # a status from Meta already settled it
    elif data.kind == gateway.REFUSED:
        message.status = Message.Status.FAILED
        message.error_code = _REFUSALS.get(data.code, SEND_REFUSED_CODE)
        message.error_message = data.message[:500] if message.error_code == SEND_REFUSED_CODE else ""
    else:
        message.status = Message.Status.SENDING
        if data.code == "whatsapp.meta_unreachable":
            message.error_code = "whatsapp_inbox.meta_unreachable"  # Meta's silence, never ERPlora's
        else:
            message.error_code = SEND_UNKNOWN_CODE if data.kind == gateway.UNKNOWN else SAAS_UNREACHABLE_CODE
        message.error_message = ""
    message.status_at = clock.now()
    message.save(
        update_fields=[
            "status",
            "status_at",
            "wa_message_id",
            "error_code",
            "error_message",
        ]
    )
    record_event(
        ctx,
        events.MESSAGE_STATUS_CHANGED,
        {
            "id": str(message.id),
            "conversation_id": str(message.conversation_id),
            "status": message.status,
        },
    )
    return {"status": message.status}


@operation(
    "whatsapp_inbox.delivery.resume",
    kind="command",
    permission=RECEIVE,
    input=ResumeIn,
    output=ResumeOut,
    ai={
        "description": "System only (the worker's scheduled task): hands erplora.com again the messages, erasures, "
        "templates and template deletions whose delivery after the COMMIT never ended.",
        "risk": "normal",
    },
)
def resume_deliveries(ctx: OperationContext, data: ResumeIn) -> dict:
    """Hand erplora.com again what was left in this hub's database, as this business."""
    cutoff = clock.now() - STUCK_AFTER
    messages = list(
        Message.objects.select_for_update(skip_locked=True)
        .filter(origin=Message.Origin.HUB, status__in=_ON_ITS_WAY, status_at__lt=cutoff)
        .order_by("status_at", "id")
        .values_list("id", flat=True)[:RESUME_BATCH]
    )
    erasures = list(
        Conversation.objects.select_for_update(skip_locked=True)
        .filter(erase_status=Conversation.EraseStatus.PENDING, erased_at__lt=cutoff)
        .order_by("erased_at", "id")
        .values_list("id", flat=True)[:RESUME_BATCH]
    )
    templates = list(
        Template.objects.select_for_update(skip_locked=True)
        .filter(submit_state__in=_TEMPLATE_ON_ITS_WAY, submit_at__lt=cutoff, deleted_at__isnull=True)
        .order_by("submit_at", "id")
        .values_list("id", flat=True)[:RESUME_BATCH]
    )
    deletions = list(
        Template.objects.select_for_update(skip_locked=True)
        .filter(delete_state=Template.DeleteState.PENDING, deleted_at__lt=cutoff)
        .order_by("deleted_at", "id")
        .values_list("id", flat=True)[:RESUME_BATCH]
    )
    for message_id in messages:
        _after_commit(ctx, deliver, message_id)
    for conversation_id in erasures:
        _after_commit(ctx, forget, conversation_id)
    for template_id in templates:
        _after_commit(ctx, submit_template, template_id)
    for template_id in deletions:
        _after_commit(ctx, remove_template, template_id)
    return {
        "messages": len(messages),
        "erasures": len(erasures),
        "templates": len(templates),
        "template_deletions": len(deletions),
    }
