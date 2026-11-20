"""The assistant's drafts (``flow.draft.*``): proposed, dismissed, or used by the automation made from one."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.flow import events
from apps.flow.models import Draft, Flow
from apps.flow.queries.drafts import DRAFT_NOT_FOUND, draft_row
from apps.flow.queries.reads import MANAGE
from apps.flow.schemas.drafts import DraftOut, DraftProposeIn, DraftRefIn

from .writes import _actor

DRAFT_DECIDED = _("That draft was already decided.")


def _decide_draft(
    ctx: OperationContext, draft_id, status: str, flow: Flow | None = None
) -> Draft:
    draft = Draft.objects.select_for_update().filter(pk=draft_id).first()
    if draft is None:
        raise NotFound(str(DRAFT_NOT_FOUND))
    if draft.status != Draft.Status.PENDING:
        raise Conflict(str(DRAFT_DECIDED), code="flow.draft_decided")
    draft.status = status
    draft.flow = flow
    draft.decided_by = _actor(ctx)
    draft.decided_at = timezone.now()
    draft.save(update_fields=["status", "flow", "decided_by", "decided_at"])
    return draft


@operation(
    "flow.draft.propose",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=DraftProposeIn,
    output=DraftOut,
    ai={
        "asks": {
            "en": (
                "create a flow that adds a task when a sale over 100 € is completed",
                "automate a thank-you WhatsApp after each appointment",
            ),
            "es": (
                "crea un flujo que deje una tarea cuando se cobre una venta de más de 100 €",
                "automatiza un WhatsApp de agradecimiento después de cada cita",
            ),
        },
        "description": "Propose a DRAFT automation — «when X happens, do Y» — whenever somebody asks for something "
        "to happen on its own («create a flow that creates a task when a sale over 100 € is completed»). "
        "It does not run, holds no permissions and waits in Automations for a person to review it and turn "
        "it on. Steps are command, condition or delay only; money is in cents (100,00 € = 10000); use "
        "the event and action names of `flow.catalog.read`. Put what you guessed in `notes`, then say it "
        "is waiting in Automations and repeat your doubts.",
        "risk": "normal",
    },
)
def propose_draft(ctx: OperationContext, data: DraftProposeIn) -> dict:
    draft = Draft.objects.create(
        name=data.name,
        definition=data.definition.model_dump(mode="json", exclude_none=True),
        notes=list(data.notes),
        created_by=_actor(ctx),
    )
    record_event(ctx, events.DRAFT_PROPOSED, {"id": str(draft.id)})
    return draft_row(draft)


@operation(
    "flow.draft.dismiss",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=MANAGE,
    input=DraftRefIn,
    output=DraftOut,
    ai={
        "asks": {
            "en": (
                "discard the assistant's draft",
                "drop that draft, I don't want it",
            ),
            "es": (
                "descarta el borrador del asistente",
                "tira ese borrador, no lo quiero",
            ),
        },
        "description": "Discard a draft the assistant proposed; it stays as a record.",
        "risk": "normal",
    },
)
def dismiss_draft(ctx: OperationContext, data: DraftRefIn) -> dict:
    draft = _decide_draft(ctx, data.id, Draft.Status.DISMISSED)
    record_event(ctx, events.DRAFT_DISMISSED, {"id": str(draft.id)})
    return draft_row(draft)
