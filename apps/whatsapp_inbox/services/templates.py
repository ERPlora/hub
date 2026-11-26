"""The team's templates (WHATSAPP_INBOX-F29…F31): create, edit, retry and delete, kept here and handed to
erplora.com after the COMMIT."""

from uuid import UUID, uuid7

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.whatsapp_inbox import clock, events, samples
from apps.whatsapp_inbox.models.templates import Template, TemplateSample, hub_writes
from apps.whatsapp_inbox.queries.channel import channel, send_blocked
from apps.whatsapp_inbox.queries.templates import TEMPLATE_GONE, live_templates, template_out, templates_of
from apps.whatsapp_inbox.schemas.templates import (
    TemplateCreateIn,
    TemplateOut,
    TemplateRefIn,
    TemplateUpdateIn,
    TemplateWriteIn,
)

from .sending import _blocked_error
from .template_handover import _TEMPLATE_ON_ITS_WAY, _apply, remove_template, submit_template
from .writes import _after_commit

TEMPLATE_EXISTS = _("There is already a template “%(name)s” in that language.")
TEMPLATE_READ_ONLY = _("This template is changed in WhatsApp Manager: the Hub cannot change it.")
TEMPLATE_IN_REVIEW = _("Meta is reviewing this template: wait for its verdict to change it.")
TEMPLATE_SUBMITTING = _("This template is on its way to Meta: wait a moment.")
TEMPLATE_CATEGORY_FIXED = _("Meta only lets you change the category of a template it rejected.")
TEMPLATE_NOT_RETRYABLE = _("There is nothing of this template to hand to Meta again.")
HEADER_FILE_MISSING = _("Choose the header's file: Meta reviews the template with it.")


def _content(data: TemplateWriteIn) -> dict:
    """What the form wrote, as the template keeps it and door 8 takes it: a header with a file names it (its text is
    refused by ``TemplateWriteIn``); any other is a text header when it has one."""
    with_file = data.header_format in samples.FILE_HEADERS
    return {
        "category": data.category,
        "header_format": data.header_format if with_file else ("TEXT" if data.header else ""),
        "header": data.header,
        "header_sample": str(data.header_sample) if with_file else None,
        "body": data.body,
        "body_examples": list(data.body_examples),
        "footer": data.footer,
        "buttons": [{field: value for field, value in button.model_dump().items() if value} for button in data.buttons],
    }


def _header_file(ctx: OperationContext, data: TemplateWriteIn) -> None:
    """A header with a file names one of this business's, of its kind (``upload_sample``)."""
    if data.header_format not in samples.FILE_HEADERS:
        return
    kept = data.header_sample is not None and TemplateSample.objects.filter(
        pk=data.header_sample, header_format=data.header_format
    ).exists()
    if not kept:
        message = str(HEADER_FILE_MISSING)
        raise InvalidPayload(message, fields={"header_sample": message})


def _no_template_without_a_number(ctx: OperationContext) -> None:
    blocked = send_blocked(channel(ctx.scope))
    if blocked in ("not_connected", "unconfigured"):
        raise _blocked_error(blocked)


def _queue(ctx: OperationContext, row: Template, key: UUID, event: str) -> None:
    row.submit_state = Template.SubmitState.QUEUED
    row.submit_key = key
    row.submit_error_code = row.submit_error = ""
    row.submit_at = clock.now()
    row.save()
    record_event(ctx, event, {"id": str(row.id)})
    _after_commit(ctx, submit_template, row.id)


@operation(
    "whatsapp_inbox.template.create",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateCreateIn,
    output=TemplateOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "create a WhatsApp template to remind appointments",
                "make a marketing template with a 10% offer",
                "add a template that says your order is ready",
            ),
            "es": (
                "crea una plantilla de WhatsApp para recordar citas",
                "haz una plantilla de marketing con una oferta del 10 %",
                "añade una plantilla con el texto: gracias por tu visita",
            ),
        },
        "description": "Creates a WhatsApp message template (name, language, utility or marketing, header, text with "
        "{{1}}… and an example of each, footer, buttons) and sends it to Meta for review. Give a new submit_key per "
        "save (the same one if you retry it): it is registered once.",
        "risk": "high",
    },
)
def create_template(ctx: OperationContext, data: TemplateCreateIn) -> dict:
    already = templates_of(ctx.scope).filter(submit_key=data.submit_key).first()
    if already is not None:
        return template_out(already)
    _no_template_without_a_number(ctx)
    _header_file(ctx, data)
    exists = Conflict(str(TEMPLATE_EXISTS % {"name": data.name}), code="whatsapp_inbox.template_exists")
    if live_templates(ctx.scope).filter(name=data.name, language=data.language).exists():
        raise exists
    row = Template(name=data.name, language=data.language, status=Template.Status.DRAFT)
    _apply(row, _content(data))
    try:
        with atomic():
            _queue(ctx, row, data.submit_key, events.TEMPLATE_CREATED)
    except IntegrityError:
        # The same save at the same time (its key), or the name just taken by another.
        twin = templates_of(ctx.scope).filter(submit_key=data.submit_key).first()
        if twin is None:
            raise exists from None
        return template_out(twin)
    return template_out(row)


def _changeable(row: Template, content: dict) -> None:
    if not hub_writes(row) or row.status in (Template.Status.DISABLED, Template.Status.DELETED):
        raise Conflict(str(TEMPLATE_READ_ONLY), code="whatsapp_inbox.template_read_only")
    if row.status == Template.Status.PENDING:
        raise Conflict(str(TEMPLATE_IN_REVIEW), code="whatsapp_inbox.template_in_review")
    in_flight = row.submit_state == Template.SubmitState.QUEUED or (
        row.submit_state == Template.SubmitState.SENDING and not row.submit_error_code
    )
    if in_flight:
        raise Conflict(str(TEMPLATE_SUBMITTING), code="whatsapp_inbox.template_submitting")
    judged = row.status not in (Template.Status.DRAFT, Template.Status.REJECTED)
    if judged and content["category"] != row.category:
        raise Conflict(str(TEMPLATE_CATEGORY_FIXED), code="whatsapp_inbox.template_category_fixed")


@operation(
    "whatsapp_inbox.template.update",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateUpdateIn,
    output=TemplateOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "change the text of the reminder template",
                "edit the welcome template and send it for review again",
                "update the promo template's footer",
            ),
            "es": (
                "cambia el texto de la plantilla de recordatorio",
                "edita la plantilla de bienvenida y mándala otra vez a revisión",
                "actualiza el pie de la plantilla de la promoción",
            ),
        },
        "description": "Changes a WhatsApp template (not its name or language) and sends it to Meta for review "
        "again; until Meta takes the change, the approved one keeps being the one sent. Not while Meta reviews it.",
        "risk": "high",
    },
)
def update_template(ctx: OperationContext, data: TemplateUpdateIn) -> dict:
    row = live_templates(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None:
        raise NotFound(str(TEMPLATE_GONE), code="whatsapp_inbox.template_not_found")
    if row.submit_key == data.submit_key:
        return template_out(row)  # the same save again
    _no_template_without_a_number(ctx)
    content = _content(data)
    _changeable(row, content)
    _header_file(ctx, data)
    if row.status == Template.Status.DRAFT:
        _apply(row, content)  # Meta never had it: what is written is the template
        row.draft = None
    else:
        row.draft = content  # Meta's stays the one sent until it takes the edit
    try:
        with atomic():
            _queue(ctx, row, data.submit_key, events.TEMPLATE_UPDATED)
    except IntegrityError:
        raise Conflict(str(TEMPLATE_SUBMITTING), code="whatsapp_inbox.template_submitting") from None
    return template_out(row)


@operation(
    "whatsapp_inbox.template.retry",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateRefIn,
    output=TemplateOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "retry sending the template to Meta",
                "the reminder template never reached Meta, try again",
                "send Meta again the template deletion it did not confirm",
            ),
            "es": (
                "vuelve a mandar la plantilla a Meta",
                "la plantilla de recordatorio no llegó a Meta, reinténtalo",
                "reintenta en Meta el borrado de la plantilla que no confirmó",
            ),
        },
        "description": "Hands a template that did not reach Meta (or a deletion Meta has not confirmed) to "
        "erplora.com again: never registered twice.",
        "risk": "normal",
    },
)
def retry_template(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = templates_of(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None or (row.deleted_at is not None and row.delete_state != Template.DeleteState.PENDING):
        raise NotFound(str(TEMPLATE_GONE), code="whatsapp_inbox.template_not_found")
    if row.delete_state == Template.DeleteState.PENDING:
        row.submit_error_code = row.submit_error = ""
        row.save(update_fields=["submit_error_code", "submit_error"])
        _after_commit(ctx, remove_template, row.id)
        return template_out(row)
    if row.submit_state == Template.SubmitState.FAILED:
        # Refused: the same key would get the same answer; a transient refusal goes again as a new save.
        _queue(ctx, row, uuid7(), events.TEMPLATE_UPDATED)
    elif row.submit_state in _TEMPLATE_ON_ITS_WAY:
        _queue(ctx, row, row.submit_key, events.TEMPLATE_UPDATED)
    else:
        raise Conflict(str(TEMPLATE_NOT_RETRYABLE), code="whatsapp_inbox.not_retryable")
    return template_out(row)


@operation(
    "whatsapp_inbox.template.delete",
    kind="command",
    permission="whatsapp_inbox.configure",
    input=TemplateRefIn,
    output=TemplateOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "delete the welcome template",
                "remove the old promo template from WhatsApp",
                "get rid of the English reminder template",
            ),
            "es": (
                "ya no queremos la plantilla de bienvenida, bórrala",
                "elimina la plantilla vieja de la promoción",
                "quita la plantilla de recordatorio en inglés",
            ),
        },
        "description": "Deletes a WhatsApp template here and at Meta (that language only). Irreversible: an approved "
        "template takes days to be approved again.",
        "risk": "high",
    },
)
def delete_template(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = live_templates(ctx.scope).select_for_update().filter(pk=data.id).first()
    if row is None:
        raise NotFound(str(TEMPLATE_GONE), code="whatsapp_inbox.template_not_found")
    # Meta may have it unless it never left the Hub (or it left and Meta refused it).
    at_meta = bool(row.meta_id) or row.status != Template.Status.DRAFT or row.submit_state == Template.SubmitState.SENDING
    row.deleted_at = clock.now()
    row.delete_state = Template.DeleteState.PENDING if at_meta else Template.DeleteState.DONE
    row.submit_state = Template.SubmitState.NONE
    row.submit_error_code = row.submit_error = ""
    row.save()
    record_event(ctx, events.TEMPLATE_DELETED, {"id": str(row.id)})
    if at_meta:
        _after_commit(ctx, remove_template, row.id)
    return template_out(row)
