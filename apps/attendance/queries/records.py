"""Your working day today, the list of working days and one day with its breaks: attendance.record.current, .list
and .detail."""

from babel.dates import format_date
from django.utils import timezone, translation
from live.context import OperationContext
from live.operations import operation

from apps.attendance.models import Break, Record
from apps.attendance.schemas import (
    CurrentOut,
    EmptyIn,
    RecordDetailOut,
    RecordListIn,
    RecordPage,
    RecordRefIn,
)
from base.business import babel_locale

from .days import _seconds, annotated, durations, effective_status, is_stale, record_out, scoped_records, visible_record
from .people import own_member
from .reads import _page, business_date, review_hours, user_name

#: How many past days «Recent days» of the clock screen shows (the old module's ten).
RECENT_DAYS = 10


def day_name(record: Record) -> str:
    """A working day as «Correct working day» names it: the person and its business day, in the active language."""
    day = format_date(record.work_date, "medium", locale=babel_locale(translation.get_language()))
    return f"{record.member_name} · {day}"


@operation(
    "attendance.record.current",
    kind="query",
    permission="attendance.clock",
    input=EmptyIn,
    output=CurrentOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how long have I worked today?",
                "am I clocked in right now?",
                "show me my working day so far",
            ),
            "es": (
                "¿cuántas horas llevo hoy?",
                "¿estoy fichado ahora?",
                "enséñame mi jornada de hoy",
            ),
        },
        "description": "Your working day today («my day», «am I clocked in?»): your staff record, whether "
        "you are clocked in or on a break and since when, today's worked and break time and your last "
        "ten days."
    },
)
def current(ctx: OperationContext, params: EmptyIn) -> dict:
    as_of = timezone.now()
    today = business_date(as_of)
    member = own_member(ctx)
    if member is None:
        return {
            "member": None,
            "open": None,
            "today": {
                "date": today,
                "worked_seconds": 0,
                "break_seconds": 0,
                "running": None,
            },
            "recent": [],
            "as_of": as_of,
        }
    hours = review_hours()
    days = annotated(Record.objects.filter(member=member))
    open_day = next(iter(days.filter(status=Record.Status.OPEN)), None)
    if open_day is not None and is_stale(open_day, hours, as_of):
        # A forgotten day: the clock offers «Clock in», which flags it and opens a new one.
        open_day = None
    worked = breaks = 0
    for record in days.filter(work_date=today):
        day_breaks, day_worked = durations(record, as_of, hours)
        breaks += day_breaks
        worked += day_worked or 0
    running = None
    if open_day is not None and open_day.work_date == today:
        running = "break" if open_day.break_started_at else "work"
    return {
        "member": {"id": member.id, "name": member.full_name},
        "open": record_out(open_day, as_of, hours) if open_day else None,
        "today": {
            "date": today,
            "worked_seconds": worked,
            "break_seconds": breaks,
            "running": running,
        },
        "recent": [
            record_out(r, as_of, hours)
            for r in days.order_by("-clock_in_at", "id")[:RECENT_DAYS]
        ],
        "as_of": as_of,
    }


@operation(
    "attendance.record.list",
    kind="query",
    permission="attendance.clock",
    input=RecordListIn,
    output=RecordPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "list this week's clock-ins",
                "show Luis's working days in October",
                "which days did Carmen clock in this month?",
            ),
            "es": (
                "¿qué fichajes hay de esta semana?",
                "muéstrame las jornadas de Luis en octubre",
                "¿qué días ha fichado Carmen este mes?",
            ),
        },
        "description": "Lists working days (clock-in, clock-out, breaks, worked time, status) with filters "
        "by person (id or name), dates and status, «mine» for your own; an employee only sees their own."
    },
)
def list_records(ctx: OperationContext, params: RecordListIn) -> dict:
    as_of = timezone.now()
    hours = review_hours()
    records = scoped_records(ctx, params, as_of, hours)
    rows = [
        record_out(r, as_of, hours)
        for r in records[params.offset : params.offset + params.limit]
    ]
    return _page(rows, records.count(), params)


@operation(
    "attendance.record.detail",
    kind="query",
    permission="attendance.clock",
    input=RecordRefIn,
    output=RecordDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me Nuria's working day on Monday with its breaks",
                "where did Pedro clock in from yesterday?",
                "who clocked Marta's day today?",
            ),
            "es": (
                "enséñame la jornada de Nuria del lunes con sus pausas",
                "¿desde dónde fichó Pedro ayer?",
                "¿quién fichó hoy por Marta?",
            ),
        },
        "description": "One working day with its breaks, where it was clocked from and who clocked it; "
        "someone else's only for whoever sees the team or corrects days."
    },
)
def record_detail(ctx: OperationContext, params: RecordRefIn) -> dict:
    as_of = timezone.now()
    hours = review_hours()
    record = visible_record(ctx, params.id)
    # A running break only runs while the day is open; on a day waiting for review it has no end.
    open_now = effective_status(record, hours, as_of) == Record.Status.OPEN
    breaks = [
        {
            "id": b.id,
            "started_at": b.started_at,
            "ended_at": b.ended_at,
            "seconds": _seconds((b.ended_at or record.clock_out_at or as_of) - b.started_at)
            if b.ended_at or record.clock_out_at or open_now
            else 0,
        }
        for b in Break.objects.filter(record=record).order_by("started_at", "id")
    ]
    return {
        **record_out(record, as_of, hours),
        "name": day_name(record),
        "in_lat": record.in_lat,
        "in_lng": record.in_lng,
        "in_accuracy_m": record.in_accuracy_m,
        "out_lat": record.out_lat,
        "out_lng": record.out_lng,
        "out_accuracy_m": record.out_accuracy_m,
        "created_by_name": user_name(record.created_by),
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "breaks": breaks,
    }
