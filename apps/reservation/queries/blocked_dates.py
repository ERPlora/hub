"""The days, or hours, the book takes no reservations (``reservation.blocked_date.list``, ``.get``).
"""

from live.context import OperationContext
from live.operations import operation

from apps.reservation.models import BlockedDate
from apps.reservation.queries.lookups import find_block
from apps.reservation.queries.rows import _page, blocked_label, blocked_out
from apps.reservation.schemas.blocked_dates import (
    BlockedDateDetailOut,
    BlockedDateListIn,
    BlockedDatePage,
    BlockedDateRefIn,
)
from base.ordering import list_order_for

BLOCKED_SORTS = {
    "date": ("date", "blocked_from"),
    "reason": ("reason", "date"),
    "is_full_day": ("is_full_day", "date"),
}


@operation(
    "reservation.blocked_date.list",
    kind="query",
    permission="reservation.view_blockeddate",
    input=BlockedDateListIn,
    output=BlockedDatePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which days are closed to bookings?",
                "show me the blocked dates",
            ),
            "es": (
                "¿qué días tengo cerrados a las reservas?",
                "enséñame las fechas bloqueadas",
            ),
        },
        "description": "Lists the days (or hours) the book takes no reservations, with their reason, by date."
    },
)
def list_blocked(ctx: OperationContext, params: BlockedDateListIn) -> dict:
    rows = BlockedDate.objects.filter(is_deleted=False)
    if params.date_from:
        rows = rows.filter(date__gte=params.date_from)
    if params.date_to:
        rows = rows.filter(date__lte=params.date_to)
    if params.is_full_day is not None:
        rows = rows.filter(is_full_day=params.is_full_day)
    return _page(
        rows.order_by(*list_order_for(params.sort, columns=BLOCKED_SORTS)), params, blocked_out
    )


@operation(
    "reservation.blocked_date.get",
    kind="query",
    permission="reservation.view_blockeddate",
    input=BlockedDateRefIn,
    output=BlockedDateDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "why is Christmas Day blocked?",
                "show me the Christmas closure block",
            ),
            "es": (
                "¿por qué está bloqueado el día de Navidad?",
                "enséñame el bloqueo del cierre por vacaciones",
                "¿qué horas cubre el bloqueo del sábado?",
            ),
        },
        "description": "Reads one blocked date (a day, or some hours of it, the book takes no reservations) with its "
        "reason: by id, or by its date when it is blocked once. A block named by its reason («the Christmas closure») is "
        "found in reservation.blocked_date.list."
    },
)
def get_blocked(ctx: OperationContext, params: BlockedDateRefIn) -> dict:
    block = find_block(params.id, params.date)
    return {**blocked_out(block), "label": blocked_label(block, ctx.language)}
