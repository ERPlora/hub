"""Who is clocked in right now and how many: attendance.presence.list and .count (the Home's «Clocked in now»)."""

import datetime as dt

from django.db.models import QuerySet
from django.utils import timezone
from live.context import OperationContext
from live.operations import operation

from apps.attendance.models import Record
from apps.attendance.schemas import EmptyIn, PresenceCountOut, PresenceListIn, PresencePage
from apps.staff.models import Member
from base.text_search import contains_text

from .days import annotated
from .reads import VIEW_ALL, _page, review_hours


def present_records() -> QuerySet:
    """Who is in: an open day within the review hours (a forgotten one is not), of a record that is not
    terminated (its person no longer works here)."""
    limit = timezone.now() - dt.timedelta(hours=review_hours())
    return Record.objects.filter(status=Record.Status.OPEN, clock_in_at__gte=limit).exclude(
        member__status=Member.Status.TERMINATED
    )


@operation(
    "attendance.presence.list",
    kind="query",
    permission=VIEW_ALL,
    input=PresenceListIn,
    output=PresencePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who is clocked in right now?",
                "who is on a break at the moment?",
                "tell me who is still working and since when",
            ),
            "es": (
                "¿quién está fichado ahora mismo?",
                "¿quién está en pausa en este momento?",
                "¿quién sigue dentro y desde qué hora entró?",
            ),
        },
        "description": "Who is clocked in right now («who is in?»): how many and who, since when and whether "
        "they are on a break. A day waiting for review does not count."
    },
)
def list_presence(ctx: OperationContext, params: PresenceListIn) -> dict:
    records = annotated(present_records())
    if params.search:
        records = records.filter(contains_text(params.search, "member_name"))
    records = records.order_by("member_name", "id")
    rows = [
        {
            "record_id": r.id,
            "member_id": r.member_id,
            "member_name": r.member_name,
            "clock_in_at": r.clock_in_at,
            "break_started_at": r.break_started_at,
            "source": r.source,
        }
        for r in records[params.offset : params.offset + params.limit]
    ]
    return _page(rows, records.count(), params)


@operation(
    "attendance.presence.count",
    kind="query",
    permission=VIEW_ALL,
    input=EmptyIn,
    output=PresenceCountOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how many are in right now?",
                "how many people have clocked in and are still here?",
                "count who is clocked in now",
            ),
            "es": (
                "¿cuántos no han fichado aún la salida?",
                "¿cuánta gente está dentro en este momento?",
                "número de fichados ahora mismo",
            ),
        },
        "description": "How many people are clocked in right now («how many are in?»), the Home's «Clocked in "
        "now». A day waiting for review does not count; for who they are, attendance.presence.list."
    },
)
def count_presence(ctx: OperationContext, params: EmptyIn) -> dict:
    return {"count": present_records().count()}
