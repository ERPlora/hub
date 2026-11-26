"""The business's message templates: which ones the Hub may change, fill or send as they are, their
list and one template."""

from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import NotFound
from live.operations import INTERNAL, operation

from apps.whatsapp_inbox.models import FILE_HEADERS, Template, TemplateSample, hub_writes
from apps.whatsapp_inbox.queries.reads import page
from apps.whatsapp_inbox.queries.reasons import template_reason
from apps.whatsapp_inbox.queries.template_samples import sample_out
from apps.whatsapp_inbox.schemas.templates import TemplateListIn, TemplateNamedOut, TemplatePage, TemplateRefIn
from base.text_search import contains_text

TEMPLATE_GONE = _("That template no longer exists.")


def templates_of(scope: Scope) -> QuerySet:
    """The templates of the business of ``scope``."""
    return Template.objects.all()


def live_templates(scope: Scope) -> QuerySet:
    """The business's templates not deleted here."""
    return templates_of(scope).filter(deleted_at__isnull=True)


def listed_templates(scope: Scope) -> QuerySet:
    """What Settings lists: the business's live templates and the ones deleted here that Meta has not deleted yet."""
    return templates_of(scope).filter(
        Q(deleted_at__isnull=True) | Q(delete_state=Template.DeleteState.PENDING)
    )


def template_editable(row: Template) -> bool:
    """Whether the Hub may change it now: content it writes (``hub_writes``: what it sends, or a file header chosen
    here), not under Meta's review, not gone."""
    return (
        hub_writes(row)
        and row.deleted_at is None
        and row.status not in (Template.Status.PENDING, Template.Status.DISABLED, Template.Status.DELETED)
    )


def template_fillable(row: Template) -> bool:
    """Whether the inbox can send it now (F33): approved and filled by the Hub, a file header with a file chosen."""
    return row.supported and row.deleted_at is None and row.status == Template.Status.APPROVED


def template_sendable(row: Template) -> bool:
    """Whether it goes as it is, with nothing to choose: a file header only with its own file."""
    return template_fillable(row) and (row.header_format not in FILE_HEADERS or row.header_sample_id is not None)


#: The approved templates the Hub fills (``template_fillable``), and those that go as they are (``template_sendable``).
_FILLABLE = Q(status=Template.Status.APPROVED, supported=True, deleted_at__isnull=True)
_SENDABLE = _FILLABLE & ~Q(header_format__in=FILE_HEADERS, header_sample__isnull=True)


def _buttons_out(buttons) -> list[dict]:
    return [
        {
            "type": str(button.get("type", "")),
            "text": str(button.get("text", "")),
            "url": str(button.get("url", "") or ""),
            "phone_number": str(button.get("phone_number", "") or ""),
        }
        for button in buttons or []
        if isinstance(button, dict)
    ]


def _its_own(row: Template) -> TemplateSample | None:
    """The template's header file."""
    return row.header_sample


def _draft_out(row: Template) -> dict | None:
    draft = row.draft
    if not draft:
        return None
    sample = draft.get("header_sample")
    kept = TemplateSample.objects.filter(pk=sample).first() if sample else None
    return {
        **draft,
        "header_format": draft.get("header_format", "TEXT" if draft.get("header") else ""),
        "header_sample": sample_out(kept),
        "buttons": _buttons_out(draft.get("buttons")),
    }


def template_out(row: Template) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "language": row.language,
        "category": row.category,
        "status": row.status,
        "header_format": row.header_format,
        "header": row.header,
        "header_sample": sample_out(_its_own(row)),
        "body": row.body,
        "body_examples": list(row.body_examples or []),
        "footer": row.footer,
        "buttons": _buttons_out(row.buttons),
        "variables": row.variables,
        "rejected_reason": row.rejected_reason,
        "meta_id": row.meta_id,
        "synced_at": row.synced_at,
        "draft": _draft_out(row),
        "submit_state": row.submit_state,
        "submit_error_code": row.submit_error_code,
        "submit_error": template_reason(row),
        "editable": template_editable(row),
        "sendable": template_sendable(row),
        "supported": row.supported,
        "deleting": row.delete_state == Template.DeleteState.PENDING,
    }


@operation(
    "whatsapp_inbox.template.list",
    kind="query",
    permission="whatsapp_inbox.reply",
    input=TemplateListIn,
    output=TemplatePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which WhatsApp templates has Meta approved?",
                "list our message templates",
                "is the welcome template still in review?",
            ),
            "es": (
                "¿cuáles de mis plantillas ha aprobado Meta?",
                "enséñame las plantillas de mensajes",
                "¿sigue en revisión la plantilla de bienvenida?",
            ),
        },
        "description": "The business's WhatsApp message templates as Meta judged them (APPROVED ones can be "
        "sent), with their text and how many variables they take; search by name."
    },
)
def list_templates(ctx: OperationContext, params: TemplateListIn) -> dict:
    rows = listed_templates(ctx.scope).select_related("header_sample")
    if params.search:
        rows = rows.filter(contains_text(params.search.strip(), "name"))
    for field in ("status", "category", "language"):
        value = getattr(params, field)
        if value:
            rows = rows.filter(**{field: value})
    if params.sendable is not None:
        rows = rows.filter(_SENDABLE if params.sendable else ~_SENDABLE)
    if params.fillable is not None:
        rows = rows.filter(_FILLABLE if params.fillable else ~_FILLABLE)
    return page(rows.order_by("name", "language", "id"), params, template_out)


# Not an assistant tool: what names a template on the card of its change, its deletion or its new hand-over to Meta
# (``schemas.fields.A_TEMPLATE``), as Settings lists it (also one deleted here that Meta still has); the model finds
# the templates in their list. Whoever sends reads the templates, as their list.
@operation(
    "whatsapp_inbox.template.get",
    kind="query",
    permission="whatsapp_inbox.reply",
    input=TemplateRefIn,
    output=TemplateNamedOut,
    ai=INTERNAL,
)
def get_template(ctx: OperationContext, data: TemplateRefIn) -> dict:
    row = listed_templates(ctx.scope).filter(pk=data.id).first()
    if row is None:
        raise NotFound(str(TEMPLATE_GONE), code="whatsapp_inbox.template_not_found")
    return {"id": row.id, "name": row.name, "language": row.language, "label": f"{row.name} ({row.language})"}
