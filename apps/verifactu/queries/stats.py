"""VeriFactu's figures (``verifactu.stats.*``): what reached the AEAT, the records by status, the queue in
short and the latest events."""

from django.db.models import Count
from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.verifactu.models import Event, Record
from apps.verifactu.schemas.fields import NoInput
from apps.verifactu.schemas.stats import (
    ComplianceSummaryOut,
    ContingencySummaryOut,
    EventsOut,
    EventsRecentIn,
    RecordsByStatusOut,
)

from .events import event_out
from .reads import VIEW
from .route import config_row


@operation(
    "verifactu.stats.compliance_summary",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=ComplianceSummaryOut,
    expose_api=True,
    ai={
        "description": "How many VeriFactu records are not in the AEAT yet, rejected, accepted and in total: whether "
        "everything reached the AEAT.",
        "asks": {
            "en": (
                "has everything reached the AEAT?",
                "is anything rejected or still not with the AEAT?",
            ),
            "es": (
                "¿ha llegado todo a Hacienda o falta algo?",
                "¿queda algo pendiente o rechazado sin llegar a la AEAT?",
            ),
        },
    },
)
def compliance_summary(ctx: OperationContext, data: NoInput) -> ComplianceSummaryOut:
    counts = dict(Record.objects.values_list("status").annotate(total=Count("id")))
    unsent = sum(counts.get(status, 0) for status in Record.UNSENT)
    rejected = counts.get(Record.Status.REJECTED, 0)
    return ComplianceSummaryOut(
        unsent_count=unsent,
        pending_count=unsent + rejected,
        rejected_count=rejected,
        accepted_count=sum(counts.get(status, 0) for status in Record.IN_AEAT),
        total=sum(counts.values()),
        environment=config_row().environment,
    )


@operation(
    "verifactu.stats.records_by_status",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=RecordsByStatusOut,
    ai={
        "description": "How many VeriFactu records are in each status.",
        "asks": {
            "en": (
                "break the VeriFactu registrations down by status",
                "VeriFactu per status: accepted, rejected and queued",
            ),
            "es": (
                "reparto de los registros de VeriFactu por estado",
                "registros aceptados, rechazados y en espera, por estado",
            ),
        },
    },
)
def records_by_status(ctx: OperationContext, data: NoInput) -> RecordsByStatusOut:
    counts = dict(Record.objects.values_list("status").annotate(total=Count("id")))
    return RecordsByStatusOut(
        rows=[
            {"status": status, "label": str(label), "total": counts.get(status, 0)}
            for status, label in Record.Status.choices
        ]
    )


@operation(
    "verifactu.stats.contingency_summary",
    kind="query",
    permission=VIEW,
    input=NoInput,
    output=ContingencySummaryOut,
    ai={
        "description": "The queue in short: how many records wait, how many are due now, and whether it is failing.",
        "asks": {
            "en": (
                "sum up the VeriFactu contingency: is it failing?",
                "how many filings to the AEAT wait, and how many are due?",
            ),
            "es": (
                "resume la contingencia de VeriFactu: ¿está fallando?",
                "¿cuántos envíos a Hacienda esperan y cuántos tocan ya?",
            ),
        },
    },
)
def contingency_summary(ctx: OperationContext, data: NoInput) -> ContingencySummaryOut:
    queued = Record.objects.filter(status__in=Record.UNSENT)
    count = queued.count()
    failing = queued.filter(attempts__gt=0).exists()
    return ContingencySummaryOut(
        queued_count=count,
        overdue_count=queued.filter(next_attempt_at__lte=timezone.now()).count(),
        severity="ok" if count == 0 else ("danger" if failing else "warning"),
    )


@operation(
    "verifactu.stats.events_recent",
    kind="query",
    permission=VIEW,
    input=EventsRecentIn,
    output=EventsOut,
    ai={
        "description": "The latest VeriFactu audit events.",
        "asks": {
            "en": (
                "what has happened lately in VeriFactu?",
                "show the ten latest fiscal events",
            ),
            "es": (
                "¿qué ha pasado últimamente en VeriFactu?",
                "dame los diez sucesos fiscales más recientes",
            ),
        },
    },
)
def events_recent(ctx: OperationContext, data: EventsRecentIn) -> EventsOut:
    events = Event.objects.select_related("record").order_by("-created_at", "-id")[
        : data.limit
    ]
    return EventsOut(rows=[event_out(event) for event in events])
