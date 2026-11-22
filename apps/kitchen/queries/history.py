"""The kitchen's history (KITCHEN-F25): what was done, by whom and when."""

import datetime as dt

from django.db.models import Q
from live.context import OperationContext
from live.operations import operation

from apps.kitchen.models import LogEntry
from apps.kitchen.queries.reads import start_of
from apps.kitchen.schemas import LogListIn, LogPage
from apps.sale.queries.people import person_names
from base.relay import by_platform


def log_row(entry: LogEntry, names: dict[str, str] | None = None) -> dict:
    """An entry of the History; ``names`` turns the username it saved into the name a person reads."""
    return {
        "id": entry.id,
        "action": entry.action,
        "ticket_id": entry.ticket_id,
        "ticket_number": entry.ticket.number,
        "item_name": entry.item.name if entry.item else "",
        "station_name": entry.station.name if entry.station else "",
        "actor": (names or {}).get(entry.actor, entry.actor),
        "by_platform": by_platform(entry.actor),
        "notes": entry.notes,
        "created_at": entry.created_at,
    }


@operation(
    "kitchen.log.list",
    kind="query",
    permission="kitchen.view_log",
    input=LogListIn,
    output=LogPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who voided number 12?",
                "what happened on the display yesterday?",
            ),
            "es": (
                "¿quién anuló la comanda 12?",
                "enséñame el historial de platos de ayer",
            ),
        },
        "description": "The kitchen's history, newest first: what happened (received, dish ready, served, "
        "cancelled…), on which ticket and dish, who did it and when; searching the ticket's number or the notes, "
        "by action and by days."
    },
)
def list_log(ctx: OperationContext, params: LogListIn) -> dict:
    entries = LogEntry.objects.select_related("ticket", "item", "station")
    if params.search:
        entries = entries.filter(
            Q(ticket__number__icontains=params.search)
            | Q(notes__icontains=params.search)
        )
    if params.action is not None:
        entries = entries.filter(action=params.action)
    if params.ticket_id is not None:
        entries = entries.filter(ticket_id=params.ticket_id)
    if params.date_from is not None:
        entries = entries.filter(created_at__gte=start_of(params.date_from))
    if params.date_to is not None:
        entries = entries.filter(
            created_at__lt=start_of(params.date_to + dt.timedelta(days=1))
        )
    entries = entries.order_by("-created_at", "-id")
    page = list(entries[params.offset : params.offset + params.limit])
    names = person_names(entry.actor for entry in page)
    return {
        "rows": [log_row(entry, names) for entry in page],
        "total": entries.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
