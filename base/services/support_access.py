"""Turning ERPlora's support access to the business on or off (``base.support_access.update``)."""

from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from base import events, queries
from base.models.support_access import SupportAccess
from base.permissions import ADMINISTER_HUB
from base.schemas.support_access import SupportAccessIn, SupportAccessOut, SupportAccessUpdateIn
from base.services.devices import _actor_label
from base.services.single_row import locked_single_row
from base.services.support_entry import end_support_sessions


@operation(
    "base.support_access.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=ADMINISTER_HUB,
    input=SupportAccessUpdateIn,
    output=SupportAccessOut,
    ai=AI(
        description=(
            "Turns on or off ERPlora's support access: on, ERPlora's support staff may enter this business to help set "
            "it up, until someone of the business turns it off; off by default."
        ),
        asks={
            "en": ("let ERPlora support in to help us set up", "turn off ERPlora's support access"),
            "es": ("deja entrar al soporte de ERPlora para que nos ayude", "quita el acceso de soporte de ERPlora"),
        },
    ),
)
def support_access_update(ctx: OperationContext, data: SupportAccessUpdateIn) -> dict:
    """«Support access»: saved at once, with who changed it; off, support leaves the business at once."""
    row = locked_single_row(SupportAccess)
    row.enabled = data.enabled
    row.updated_by = _actor_label(ctx)
    row.save()
    if not data.enabled:
        end_support_sessions(ctx.scope.key)
    record_event(ctx, events.SUPPORT_ACCESS_CHANGED, {"enabled": data.enabled})
    return queries.support_access.support_access_get(ctx, SupportAccessIn())
