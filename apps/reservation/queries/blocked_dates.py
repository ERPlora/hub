"""The days (or hours) the book takes no reservations: the list, and one by id or by its date."""

import datetime as dt
from uuid import UUID

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.reservation.models import BlockedDate
from apps.reservation.queries.naming import _named, _said_day, _said_hours
from apps.reservation.queries.reads import _page, blocked_out
from apps.reservation.schemas.blocked_dates import (
    BlockedDateDetailOut,
    BlockedDateListIn,
    BlockedDatePage,
    BlockedDateRefIn,
)
from base.ordering import list_order_for

BLOCK_NOT_FOUND = _("That blocked date does not exist in this business.")
BLOCK_AMBIGUOUS = _("That date is blocked at several times: say which one by its id.")


def blocked_label(block: BlockedDate, language: str) -> str:
    """As the blocked dates' list says one: its day and, when it blocks only some hours, those hours."""
    hours = (
        ""
        if block.is_full_day
        else _said_hours(block.blocked_from, block.blocked_until, language)
    )
    return _named(_said_day(block.date, language), hours)


def find_block(
    block_id: UUID | None, day: dt.date | None, *, lock: bool = False
) -> BlockedDate:
    """A live blocked date by id or by its day, when that day is blocked once."""
    rows = BlockedDate.objects.filter(is_deleted=False)
    if lock:
        rows = rows.select_for_update()
    rows = rows.filter(pk=block_id) if block_id is not None else rows.filter(date=day)
    found = list(rows[:2])
    if not found:
        raise NotFound(str(BLOCK_NOT_FOUND), code="reservation.blocked_date_not_found")
    if len(found) > 1:
        raise Conflict(str(BLOCK_AMBIGUOUS), code="reservation.blocked_date_ambiguous")
    return found[0]


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
