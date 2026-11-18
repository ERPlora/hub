"""VeriFactu's audit trail (``verifactu.event.list``): its events, each message in the reader's language."""

from functools import reduce
from operator import and_

from django.db.models import Case, Q, When
from live.context import OperationContext
from live.operations import operation

from apps.verifactu.models import Event
from apps.verifactu.schemas import EventListIn, EventOut, Page

from .reads import VIEW, page


def event_out(event: Event) -> EventOut:
    return EventOut(
        id=event.id,
        created_at=event.created_at,
        kind=event.kind,
        severity=event.severity,
        message=event.message(),
        record_id=event.record_id,
        invoice_number=event.record.invoice_number if event.record_id else "",
    )


def _words(text: str | None) -> list[str]:
    return [word for word in (text or "").split() if word]


@operation(
    "verifactu.event.list",
    kind="query",
    permission=VIEW,
    input=EventListIn,
    output=Page[EventOut],
    ai={
        "description": "VeriFactu's audit events, newest first, each message in the reader's language: search by the "
        "words shown (in Spanish or English), filter by type, severity and day.",
        "asks": {
            "en": (
                "search VeriFactu's audit trail for errors",
                "which serious warnings did VeriFactu note down?",
            ),
            "es": (
                "busca errores en el historial de auditoría de VeriFactu",
                "¿qué incidencias graves ha apuntado VeriFactu?",
            ),
        },
    },
)
def list_events(ctx: OperationContext, data: EventListIn) -> dict:
    queryset = Event.objects.select_related("record")
    words = _words(data.search)
    if words:
        queryset = queryset.filter(
            reduce(and_, (Q(search_text__icontains=word.lower()) for word in words))
        )
    if data.kind:
        queryset = queryset.filter(kind=data.kind)
    if data.severity:
        queryset = queryset.filter(severity=data.severity)
    if data.date_from:
        queryset = queryset.filter(created_at__date__gte=data.date_from)
    if data.date_to:
        queryset = queryset.filter(created_at__date__lte=data.date_to)
    prefix = "-" if data.dir == "desc" else ""
    column = data.sort or "created_at"
    # Severity sorts by weight (debug → critical ascending), not alphabetically.
    if column == "severity":
        weight = Case(*(When(severity=code, then=index) for index, code in enumerate(Event.Severity.values)))
        queryset = queryset.annotate(weight=weight).order_by(f"{prefix}weight", "-created_at", "-id")
    else:
        queryset = queryset.order_by(f"{prefix}{column}", f"{prefix}id")
    return page(queryset, data.limit, data.offset, event_out)
