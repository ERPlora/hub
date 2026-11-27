"""The hold a reservation of Reservations keeps on its table (``table.hold.by_reservation``), while it holds it."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound
from live.operations import operation

from apps.table.models import Hold
from apps.table.schemas.holds import HoldByReservationIn, HoldOut

HOLD_NOT_FOUND = _(
    "That hold is not there any more: it was released, it expired, or that booking never held a table."
)


def hold_row(hold: Hold) -> dict:
    return {
        "id": hold.pk,
        "table_id": hold.table_id,
        "source": hold.source,
        "source_ref": hold.source_ref,
        "held_from": hold.held_from,
        "held_until": hold.held_until,
        "party_size": hold.party_size,
        "label": hold.label,
        "status": hold.status,
    }


@operation(
    "table.hold.by_reservation",
    kind="query",
    permission="table.view_table",
    input=HoldByReservationIn,
    output=HoldOut,
    expose_api=True,
    ai={
        "description": "Get the hold a reservation of Reservations keeps on its table, while it holds it: the table, "
        "its window and the name it paints on the table.",
        "asks": {
            "en": (
                "which table is Ana's booking holding?",
                "what table did we keep for the Garcia reservation?",
            ),
            "es": (
                "¿qué mesa tiene guardada la reserva de Ana?",
                "¿qué mesa retiene la reserva de los García?",
            ),
        },
    },
)
def hold_by_reservation(ctx: OperationContext, params: HoldByReservationIn) -> dict:
    hold = (
        Hold.objects.filter(
            source=Hold.Source.RESERVATION,
            source_ref=str(params.reservation_id),
            status=Hold.Status.HELD,
            held_until__gt=timezone.now(),
        )
        .order_by("held_from", "id")
        .first()
    )
    if hold is None:
        raise NotFound(str(HOLD_NOT_FOUND), code="table.hold_not_found")
    return hold_row(hold)
