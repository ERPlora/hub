"""Handing a template to erplora.com and Meta (doors 8 and 9) outside any transaction, and
recording erplora.com's answer in a short transaction of its own."""

import base64
import logging
from uuid import UUID

from django.core.files.storage import storages
from live.context import OperationContext, Scope, system_context
from live.operations import get, operation
from live.outbox import record_event

from apps.whatsapp_inbox import clock, events, gateway, samples
from apps.whatsapp_inbox.models.templates import Template, TemplateSample
from apps.whatsapp_inbox.queries.reasons import (
    HEADER_SAMPLE_MISSING_CODE,
    SAAS_UNREACHABLE_CODE,
    SEND_UNKNOWN_CODE,
    TEMPLATE_REFUSED_CODE,
)
from apps.whatsapp_inbox.queries.templates import templates_of
from apps.whatsapp_inbox.schemas.deliveries import RecordOut
from apps.whatsapp_inbox.schemas.template_handover import (
    ClaimTemplateDeletionOut,
    ClaimTemplateOut,
    RecordTemplateDeletionIn,
    RecordTemplateIn,
)
from apps.whatsapp_inbox.schemas.templates import TemplateRefIn, template_variables
from base import outbound
from base.files.store import STORE_ERRORS

from .writes import RECEIVE

logger = logging.getLogger(__name__)

#: erplora.com's 409 codes for a template the Hub says in its own words when read (never blaming ERPlora for
#: Meta); any other is Meta's refusal, with Meta's reason as it came.
_TEMPLATE_REFUSALS = {
    "whatsapp.meta_unreachable": "whatsapp_inbox.meta_unreachable",
    "whatsapp.meta_rate_limited": "whatsapp_inbox.meta_rate_limited",
    "whatsapp.not_connected": "whatsapp_inbox.channel_not_connected",
    "whatsapp.reconnect_needed": "whatsapp_inbox.reconnect_needed",
    HEADER_SAMPLE_MISSING_CODE: HEADER_SAMPLE_MISSING_CODE,
}
_TEMPLATE_ON_ITS_WAY = (Template.SubmitState.QUEUED, Template.SubmitState.SENDING)


def _apply(row: Template, content: dict) -> None:
    for field in ("category", "header", "body", "body_examples", "footer", "buttons"):
        setattr(row, field, content[field])
    # An edit kept before headers had files carries neither: a text header or none.
    row.header_format = content.get("header_format", "TEXT" if row.header else "")
    row.header_sample_id = content.get("header_sample")
    row.variables = template_variables(row.body)


def submit_template(scope: Scope, template_id: UUID) -> None:
    """Hand a template to erplora.com (door 8) with no transaction and no lock around the HTTP call; its
    answer is recorded in a transaction of its own. A header's file is read from the store then too, with no
    connection held: one no longer there is said with its own code (fixed with Edit), the store not answering is
    «nothing left», to send again."""
    system = system_context(scope)
    claimed = get("whatsapp_inbox.template.claim_submit")(system, TemplateRefIn(id=template_id))
    if not claimed.claimed:
        return
    outbound.release()  # erplora.com is waited for with no connection held
    template, reply = _with_its_file(claimed.template)
    if reply is None:
        try:
            reply = gateway.submit_template(
                hub=scope.key, idempotency_key=str(claimed.submit_key), template=template
            )
        except gateway.NotConfigured:
            reply = gateway.Reply(kind=gateway.UNREACHABLE, message="SAAS_INTERNAL_URL is not set.")
    get("whatsapp_inbox.template.record_submit")(
        system,
        RecordTemplateIn(
            id=template_id,
            submit_key=claimed.submit_key,
            kind=reply.kind,
            meta_id=reply.meta_id,
            status=reply.status,
            code=reply.code,
            message=reply.message,
        ),
    )


def _with_its_file(template: dict) -> tuple[dict, gateway.Reply | None]:
    """Door 8's body with the header's file in base64 (``sample_key`` → ``header_sample``), or the reply of a file
    that could not be read."""
    key = template.pop("sample_key", None)
    name = template.pop("sample_name", "")
    if key is None:
        return template, None
    missing = gateway.Reply(kind=gateway.REFUSED, code=HEADER_SAMPLE_MISSING_CODE)
    if not key:
        return template, missing
    try:
        with storages["hub_files"].open(key, "rb") as kept:
            content = kept.read()
    except FileNotFoundError:
        logger.error("whatsapp_inbox.template.sample_missing key=%s", key)
        return template, missing
    except STORE_ERRORS:
        logger.exception("whatsapp_inbox.template.sample_unreadable key=%s", key)
        return template, gateway.Reply(kind=gateway.UNREACHABLE, message="The hub's file store did not answer.")
    sample = {"name": name, "content_base64": base64.b64encode(content).decode("ascii")}
    return {**template, "header_sample": sample}, None


def remove_template(scope: Scope, template_id: UUID) -> None:
    """Ask erplora.com to delete a template deleted here at Meta (door 9), outside any transaction."""
    system = system_context(scope)
    claimed = get("whatsapp_inbox.template.claim_delete")(system, TemplateRefIn(id=template_id))
    if not claimed.claimed:
        return
    outbound.release()  # erplora.com is waited for with no connection held
    try:
        reply = gateway.delete_template(
            hub=scope.key, name=claimed.name, language=claimed.language, meta_id=claimed.meta_id
        )
    except gateway.NotConfigured:
        reply = gateway.Reply(kind=gateway.UNREACHABLE, message="SAAS_INTERNAL_URL is not set.")
    get("whatsapp_inbox.template.record_delete")(
        system, RecordTemplateDeletionIn(id=template_id, kind=reply.kind, code=reply.code, message=reply.message)
    )


@operation(
    "whatsapp_inbox.template.claim_submit",
    kind="command",
    permission=RECEIVE,
    input=TemplateRefIn,
    output=ClaimTemplateOut,
    ai={"description": "System only: takes a template to hand to erplora.com (nobody else is on it).", "risk": "normal"},
)
def claim_submit(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = (
        templates_of(ctx.scope).select_for_update(skip_locked=True)
        .filter(pk=data.id, submit_state__in=_TEMPLATE_ON_ITS_WAY, deleted_at__isnull=True)
        .first()
    )
    if row is None:
        return {"claimed": False}
    row.submit_state = Template.SubmitState.SENDING
    row.submit_at = clock.now()
    row.save(update_fields=["submit_state", "submit_at"])
    content = dict(row.draft or {
        "category": row.category,
        "header_format": row.header_format,
        "header": row.header,
        "header_sample": str(row.header_sample_id) if row.header_sample_id else None,
        "body": row.body,
        "body_examples": row.body_examples,
        "footer": row.footer,
        "buttons": row.buttons,
    })
    header_format = content.pop("header_format", "")
    sample_id = content.pop("header_sample", None)
    template = {"name": row.name, "language": row.language, **content, "meta_id": row.meta_id}
    if header_format in samples.FILE_HEADERS:
        # Read after the claim's COMMIT, with no connection held (``submit_template``): the key, not the bytes.
        sample = TemplateSample.objects.filter(pk=sample_id).first() if sample_id else None
        template.update(header_format=header_format)
        if sample is not None:
            template.update(sample_key=sample.key, sample_name=sample.name)
        else:
            template.update(sample_key="", sample_name="")
    return {"claimed": True, "template": template, "submit_key": row.submit_key}


def _template_failure(kind: str, code: str, message: str) -> tuple[str, str]:
    """The Hub's code of a hand-over or deletion that did not end well and, for a refusal of Meta's it has no name for,
    Meta's reason as it came; the Hub's own words are said when the row is read (queries.reasons.template_reason)."""
    if kind == gateway.REFUSED:
        known = _TEMPLATE_REFUSALS.get(code)
        if known:
            return known, ""
        return TEMPLATE_REFUSED_CODE, message[:500]
    return (SEND_UNKNOWN_CODE if kind == gateway.UNKNOWN else SAAS_UNREACHABLE_CODE), ""


@operation(
    "whatsapp_inbox.template.record_submit",
    kind="command",
    permission=RECEIVE,
    input=RecordTemplateIn,
    output=RecordOut,
    ai={
        "description": "System only: records erplora.com's answer to a template: Meta took it (its id and verdict), "
        "refused it with its reason, or no answer (to retry with the same key).",
        "risk": "normal",
    },
)
def record_submit(ctx: OperationContext, data: RecordTemplateIn) -> dict:
    row = templates_of(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None:
        return {"status": None}
    if row.submit_key != data.submit_key or row.submit_state not in _TEMPLATE_ON_ITS_WAY:
        return {"status": row.status}  # an answer to an older save, or the template was deleted meanwhile
    if data.kind == gateway.ACCEPTED:
        if row.draft:
            _apply(row, row.draft)
            row.draft = None
        row.status = data.status
        row.meta_id = data.meta_id
        row.rejected_reason = ""
        row.submit_state = Template.SubmitState.NONE
        row.submit_error_code = row.submit_error = ""
    else:
        row.submit_error_code, row.submit_error = _template_failure(data.kind, data.code, data.message)
        row.submit_state = (
            Template.SubmitState.FAILED if data.kind == gateway.REFUSED else Template.SubmitState.SENDING
        )
    row.submit_at = clock.now()
    row.save()
    record_event(ctx, events.TEMPLATE_UPDATED, {"id": str(row.id)})
    return {"status": row.status}


@operation(
    "whatsapp_inbox.template.claim_delete",
    kind="command",
    permission=RECEIVE,
    input=TemplateRefIn,
    output=ClaimTemplateDeletionOut,
    ai={"description": "System only: takes a template deleted here that Meta still has to delete.", "risk": "normal"},
)
def claim_delete(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = (
        templates_of(ctx.scope).select_for_update(skip_locked=True)
        .filter(pk=data.id, delete_state=Template.DeleteState.PENDING)
        .first()
    )
    if row is None:
        return {"claimed": False}
    return {"claimed": True, "name": row.name, "language": row.language, "meta_id": row.meta_id}


@operation(
    "whatsapp_inbox.template.record_delete",
    kind="command",
    permission=RECEIVE,
    input=RecordTemplateDeletionIn,
    output=RecordOut,
    ai={
        "description": "System only: records that erplora.com deleted a template at Meta; unconfirmed, it is asked again.",
        "risk": "normal",
    },
)
def record_delete(ctx: OperationContext, data: RecordTemplateDeletionIn) -> dict:
    row = templates_of(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None or row.delete_state != Template.DeleteState.PENDING:
        return {"status": row.delete_state if row else None}
    if data.kind == gateway.ACCEPTED:
        row.delete_state = Template.DeleteState.DONE
        row.submit_error_code = row.submit_error = ""
    else:
        row.submit_error_code, row.submit_error = _template_failure(data.kind, data.code, data.message)
    row.save(update_fields=["delete_state", "submit_error_code", "submit_error"])
    record_event(ctx, events.TEMPLATE_UPDATED, {"id": str(row.id)})
    return {"status": row.delete_state}
