"""Whether ERPlora's support may come into the business, and who of support came in (``base.support_access.get``)."""

from live.context import OperationContext
from live.operations import AI, operation

from base.models.support_access import SupportAccess, SupportVisit
from base.permissions import ADMINISTER_HUB, VIEW_HOME
from base.schemas.support_access import SupportAccessIn, SupportAccessOut

#: How many entries of support the setting shows, the most recent first.
RECENT_VISITS = 10


@operation(
    "base.support_access.get",
    kind="query",
    permission=VIEW_HOME,
    input=SupportAccessIn,
    output=SupportAccessOut,
    ai=AI(
        description=(
            "Says whether ERPlora's support staff may enter this business to help set it up, who changed that last, "
            "whether who asks may change it, and the last times support entered (who and when)."
        ),
        asks={
            "en": ("can ERPlora support get into our business?", "who from ERPlora support has entered?"),
            "es": ("¿puede entrar el soporte de ERPlora en el negocio?", "¿quién de soporte de ERPlora ha entrado?"),
        },
    ),
)
def support_access_get(ctx: OperationContext, data: SupportAccessIn) -> dict:
    """«Support access» in Settings › General; off without a row."""
    row = SupportAccess.objects.first()
    visits = SupportVisit.objects.order_by("-entered_at", "-id")[:RECENT_VISITS]
    return {
        "enabled": bool(row is not None and row.enabled),
        "can_change": ctx.has(ADMINISTER_HUB),
        "updated_by": row.updated_by if row is not None else "",
        "updated_at": row.updated_at if row is not None else None,
        "visits": [
            {"person": visit.name or visit.email or visit.username, "entered_at": visit.entered_at} for visit in visits
        ],
    }
