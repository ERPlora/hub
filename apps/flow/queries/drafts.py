"""The assistant's drafts (``flow.draft.list`` and ``flow.draft.get``)."""

from typing import Any

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.flow.models import Draft
from apps.flow.schemas.drafts import DraftListIn, DraftOut, DraftRefIn
from apps.flow.schemas.fields import Page

from .reads import VIEW

DRAFT_NOT_FOUND = _("That draft does not exist in this business.")


def draft_row(draft: Draft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "name": draft.name,
        "definition": draft.definition,
        "notes": draft.notes,
        "status": draft.status,
        "flow_id": draft.flow_id,
        "created_at": draft.created_at,
        "created_by": draft.created_by,
    }


@operation(
    "flow.draft.list",
    kind="query",
    permission=VIEW,
    input=DraftListIn,
    output=Page[DraftOut],
    ai={
        "asks": {
            "en": (
                "which drafts did the assistant leave me?",
                "are there automation drafts waiting for me?",
            ),
            "es": (
                "¿qué borradores me ha dejado el asistente?",
                "¿hay borradores de automatizaciones pendientes?",
            ),
        },
        "description": "The automations the assistant proposed that are waiting for a person, the newest first."
    },
)
def list_drafts(ctx: OperationContext, data: DraftListIn) -> dict:
    drafts = Draft.objects.filter(status=Draft.Status.PENDING)
    total = drafts.count()
    page = drafts.order_by("-created_at", "-id")[data.offset : data.offset + data.limit]
    return {
        "rows": [draft_row(draft) for draft in page],
        "total": total,
        "limit": data.limit,
        "offset": data.offset,
    }


@operation(
    "flow.draft.get",
    kind="query",
    permission=VIEW,
    input=DraftRefIn,
    output=DraftOut,
    ai={
        "asks": {
            "en": (
                "show me the draft you proposed",
                "what doubts does the draft automation have?",
            ),
            "es": (
                "enséñame el borrador que me propusiste",
                "¿qué dudas tiene el borrador de la automatización?",
            ),
        },
        "description": "One draft the assistant proposed, by its id: its name, its steps, what it could not work out "
        "and whether it still waits, was used or was discarded."
    },
)
def get_draft(ctx: OperationContext, data: DraftRefIn) -> dict:
    found = Draft.objects.filter(pk=data.id).first()
    if found is None:
        with translation.override(ctx.language):
            raise NotFound(str(DRAFT_NOT_FOUND))
    return draft_row(found)
