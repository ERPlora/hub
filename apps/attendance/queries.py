"""Read operations of the attendance app, and the lookups services.py shares (WORKBOOK «Servicios»).

Every query runs READ ONLY. Who sees what: whoever clocks sees their own working days and their history
(the law makes them accessible to the worker); ``attendance.view_all`` sees the team. «Own» is every day
of a staff record linked to the caller's user (a rehired person keeps their old days). Durations are
computed here, in seconds, as of the moment the query runs (``as_of``); the screens make them run on
from there. A day waiting for review has no worked time: «until now» would count days nobody worked.
"""

import calendar
import csv
import datetime as dt
import io
from typing import Any
from uuid import UUID

from django.db.models import (
    CharField,
    Count,
    DateTimeField,
    DurationField,
    F,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import operation

from apps.attendance.models import AttendanceSettings, Break, Correction, Record
from apps.attendance.schemas import (
    CorrectionListIn,
    CorrectionPage,
    CurrentOut,
    EmptyIn,
    ExportOut,
    PersonListIn,
    PersonPage,
    PresenceListIn,
    PresencePage,
    RecordDetailOut,
    RecordExportIn,
    RecordListIn,
    RecordPage,
    RecordRefIn,
    SettingsOut,
)
from apps.staff.models import Member

MEMBER_NOT_FOUND = _("That person does not exist in Staff.")
AMBIGUOUS_MEMBER = _("Several people match “%(name)s”: %(matches)s. Say which one.")
RECORD_NOT_FOUND = _("That working day does not exist in this business.")
OWN_DAYS_ONLY = _("You can only see your own working days.")
#: The reason of the system's correction when a termination closes a day (ATTENDANCE-F13). Stored in
#: English, the source, and shown in the reader's language.
TERMINATED_REASON = _("Day closed when the person was terminated in Staff.")
TERMINATED_REASON_SOURCE = "Day closed when the person was terminated in Staff."
SYSTEM_REASONS = frozenset({TERMINATED_REASON_SOURCE})

VIEW_ALL = "attendance.view_all"
#: How many past days «Recent days» of the clock screen shows (the old module's ten).
RECENT_DAYS = 10
#: The CSV of the old module, column for column (WORKBOOK ATTENDANCE-F10).
CSV_HEADER = (
    "date",
    "user",
    "clock_in",
    "clock_out",
    "break_minutes",
    "worked_minutes",
    "status",
    "within_radius_in",
    "within_radius_out",
)
#: What a spreadsheet runs as a formula when a cell starts with it (OWASP «CSV injection»).
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
#: The settings until the business saves its own (the old module's table defaults).
DEFAULTS = {
    "require_location": False,
    "geofence_radius_m": 100,
    "workplace_lat": None,
    "workplace_lng": None,
    "auto_close_after_hours": 12,
}


# ── Lookups shared with services.py ─────────────────────────────────────────────────────────────


def member_name_expression() -> Concat:
    return Concat("first_name", Value(" "), "last_name", output_field=CharField())


def actor_user(ctx: OperationContext) -> Any | None:
    """The user behind the context; ``None`` for the platform itself or an anonymous caller."""
    return ctx.actor if hasattr(ctx.actor, "get_username") else None


def user_name(user: Any | None) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or user.get_username()).strip()


def own_member(ctx: OperationContext) -> Member | None:
    """The live (not terminated) staff record linked to the caller's user, if any."""
    user = actor_user(ctx)
    if user is None:
        return None
    return (
        Member.objects.exclude(status=Member.Status.TERMINATED)
        .filter(user_id=user.pk)
        .first()
    )


def find_member(
    member_id: UUID | None, name: str | None, *, include_terminated: bool = False
) -> Member:
    """The staff record named by id, or by name: an exact full name first, then a part of it.

    ``NotFound`` when nothing matches; 409 ``attendance.ambiguous_member`` naming the candidates.
    """
    members = Member.objects.annotate(full=member_name_expression())
    if not include_terminated:
        members = members.exclude(status=Member.Status.TERMINATED)
    member = None
    if member_id is not None:
        member = members.filter(pk=member_id).first()
    elif name:
        text = name.strip()
        matches = list(members.filter(full__iexact=text)[:2]) or list(
            members.filter(full__icontains=text).order_by(
                "first_name", "last_name", "id"
            )[:6]
        )
        if len(matches) > 1:
            names = ", ".join(m.full_name for m in matches[:5])
            raise Conflict(
                str(AMBIGUOUS_MEMBER) % {"name": text, "matches": names},
                code="attendance.ambiguous_member",
            )
        member = matches[0] if matches else None
    if member is None:
        raise NotFound(str(MEMBER_NOT_FOUND))
    return member


def saved_settings() -> AttendanceSettings | None:
    return AttendanceSettings.objects.filter(slot=1).first()


def settings_values(row: AttendanceSettings | None) -> dict:
    values = dict(DEFAULTS)
    if row is not None:
        values.update({key: getattr(row, key) for key in DEFAULTS})
    return {
        **values,
        "workplace_set": values["workplace_lat"] is not None
        and values["workplace_lng"] is not None,
        "saved": row is not None,
        "updated_at": row.updated_at if row is not None else None,
    }


def annotated(records: QuerySet) -> QuerySet:
    """Working days with what their row shows: the person's name, the breaks and the corrections."""
    closed = (
        Break.objects.filter(record=OuterRef("pk"), ended_at__isnull=False)
        .values("record")
        .annotate(
            total=Sum(F("ended_at") - F("started_at"), output_field=DurationField())
        )
        .values("total")
    )
    running = Break.objects.filter(record=OuterRef("pk"), ended_at__isnull=True).values(
        "started_at"
    )[:1]
    breaks = (
        Break.objects.filter(record=OuterRef("pk"))
        .values("record")
        .annotate(n=Count("id"))
        .values("n")
    )
    corrections = (
        Correction.objects.filter(record=OuterRef("pk"))
        .values("record")
        .annotate(n=Count("id"))
        .values("n")
    )
    return records.select_related("member").annotate(
        member_name=Concat(
            "member__first_name",
            Value(" "),
            "member__last_name",
            output_field=CharField(),
        ),
        closed_break=Subquery(closed, output_field=DurationField()),
        break_started_at=Subquery(running, output_field=DateTimeField()),
        break_count=Coalesce(Subquery(breaks, output_field=IntegerField()), 0),
        correction_count=Coalesce(
            Subquery(corrections, output_field=IntegerField()), 0
        ),
    )


def _seconds(delta: dt.timedelta) -> int:
    return max(0, int(delta.total_seconds()))


def review_hours() -> int:
    """After how many hours an open day waits for review (the settings, 12 until saved)."""
    return settings_values(saved_settings())["auto_close_after_hours"]


def is_stale(record: Record, hours: int, now: dt.datetime) -> bool:
    """An open day older than ``hours``: a forgotten clock-out (ATTENDANCE-F05).

    It reads as waiting for review whether or not the scheduled review has flagged it yet (phase 1 has
    no worker): it never counts «until now», and only a manager's correction closes it.
    """
    return record.status == Record.Status.OPEN and record.clock_in_at + dt.timedelta(hours=hours) < now


def effective_status(record: Record, hours: int, as_of: dt.datetime) -> str:
    return Record.Status.NEEDS_REVIEW if is_stale(record, hours, as_of) else record.status


def durations(record: Record, as_of: dt.datetime, hours: int) -> tuple[int, int | None]:
    """``(break_seconds, worked_seconds)`` of an annotated day as of ``as_of``.

    Only an open day (or a closed one) has an end to measure against: a day waiting for review has no
    worked time, and its running break does not grow either (its end is unknown).
    """
    status = effective_status(record, hours, as_of)
    closed = _seconds(record.closed_break) if record.closed_break else 0
    running = 0
    if record.break_started_at is not None and (record.clock_out_at or status == Record.Status.OPEN):
        running = _seconds((record.clock_out_at or as_of) - record.break_started_at)
    breaks = closed + running
    end = record.clock_out_at or (as_of if status == Record.Status.OPEN else None)
    worked = None if end is None else max(0, _seconds(end - record.clock_in_at) - breaks)
    return breaks, worked


def record_out(record: Record, as_of: dt.datetime, hours: int) -> dict:
    breaks, worked = durations(record, as_of, hours)
    return {
        "id": record.id,
        "member_id": record.member_id,
        "member_name": record.member_name,
        "work_date": record.work_date,
        "clock_in_at": record.clock_in_at,
        "clock_out_at": record.clock_out_at,
        "status": effective_status(record, hours, as_of),
        "source": record.source,
        "in_distance_m": record.in_distance_m,
        "in_within_radius": record.in_within_radius,
        "out_distance_m": record.out_distance_m,
        "out_within_radius": record.out_within_radius,
        "note": record.note,
        "break_count": record.break_count,
        "break_seconds": breaks,
        "worked_seconds": worked,
        "break_started_at": record.break_started_at,
        "correction_count": record.correction_count,
        "as_of": as_of,
    }


def load_record(record_id: UUID, as_of: dt.datetime | None = None) -> dict:
    """One day as services.py returns it after a write."""
    record = annotated(Record.objects.filter(pk=record_id)).get()
    return record_out(record, as_of or timezone.now(), review_hours())


def _owns(ctx: OperationContext, record: Record) -> bool:
    user = actor_user(ctx)
    return user is not None and record.member.user_id == user.pk


def visible_record(ctx: OperationContext, record_id: UUID) -> Record:
    """A day the caller may see (their own, or any with view_all); ``NotFound`` otherwise."""
    record = annotated(Record.objects.filter(pk=record_id)).first()
    if record is None or not (ctx.has(VIEW_ALL) or _owns(ctx, record)):
        raise NotFound(str(RECORD_NOT_FOUND))
    return record


def _own_days(ctx: OperationContext) -> Q | None:
    user = actor_user(ctx)
    return None if user is None else Q(member__user_id=user.pk)


def scoped_records(ctx: OperationContext, params: RecordListIn, as_of: dt.datetime, hours: int) -> QuerySet:
    """The days of the list and the CSV: the caller's own unless they see the team, then the filters.

    The status filter reads the status a day shows: a forgotten open day is «needs review».
    """
    records = Record.objects.all()
    own = _own_days(ctx)
    named = params.member_id is not None or bool(params.member)
    if named:
        member = find_member(params.member_id, params.member, include_terminated=True)
        if not ctx.has(VIEW_ALL) and (
            own is None or member.user_id != actor_user(ctx).pk
        ):
            raise PermissionDenied(str(OWN_DAYS_ONLY))
        records = records.filter(member=member)
    if params.mine or not ctx.has(VIEW_ALL):
        records = records.filter(own) if own is not None else records.none()
    if params.status:
        limit = as_of - dt.timedelta(hours=hours)
        if params.status == Record.Status.OPEN:
            records = records.filter(status=Record.Status.OPEN, clock_in_at__gte=limit)
        elif params.status == Record.Status.NEEDS_REVIEW:
            records = records.filter(
                Q(status=Record.Status.NEEDS_REVIEW) | Q(status=Record.Status.OPEN, clock_in_at__lt=limit)
            )
        else:
            records = records.filter(status=params.status)
    if params.date_from:
        records = records.filter(work_date__gte=params.date_from)
    if params.date_to:
        records = records.filter(work_date__lte=params.date_to)
    records = annotated(records)
    if params.search:
        records = records.filter(member_name__icontains=params.search)
    return records.order_by(params.sort, "id")


def _page(rows: list, total: int, params) -> dict:
    return {
        "rows": rows,
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


def correction_out(trail: Correction) -> dict:
    system = trail.is_system
    return {
        "id": trail.id,
        "record_id": trail.record_id,
        "old_clock_in_at": trail.old_clock_in_at,
        "old_clock_out_at": trail.old_clock_out_at,
        "old_status": trail.old_status,
        "new_clock_in_at": trail.new_clock_in_at,
        "new_clock_out_at": trail.new_clock_out_at,
        "new_status": trail.new_status,
        # A system reason is stored in English and read in the reader's language.
        "reason": gettext(trail.reason)
        if system and trail.reason in SYSTEM_REASONS
        else trail.reason,
        "is_system": system,
        # The name copied when the correction was made: it outlives the user.
        "created_by_name": trail.created_by_name,
        "created_at": trail.created_at,
    }


def business_date(instant: dt.datetime) -> dt.date:
    """The business's calendar day of an instant (phase 1: ``settings.TIME_ZONE``, Europe/Madrid)."""
    return timezone.localdate(instant)


# ── Operations ──────────────────────────────────────────────────────────────────────────────────


@operation(
    "attendance.record.current",
    kind="query",
    permission="attendance.clock",
    input=EmptyIn,
    output=CurrentOut,
    expose_api=True,
    ai={
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
        "description": "One working day with its breaks, where it was clocked from and who clocked it; "
        "someone else's only for whoever sees the team."
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


def export_filename(date_from: dt.date | None, date_to: dt.date | None) -> str:
    """``attendance-2026-10.csv`` for a whole month, the dates for another range, else ``attendance.csv``."""
    if date_from is None or date_to is None:
        return "attendance.csv"
    last_day = calendar.monthrange(date_from.year, date_from.month)[1]
    if date_from.day == 1 and date_to == date_from.replace(day=last_day):
        return f"attendance-{date_from:%Y-%m}.csv"
    return f"attendance-{date_from.isoformat()}_{date_to.isoformat()}.csv"


def _cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_STARTS) else text


def _local(instant: dt.datetime | None) -> str:
    return (
        ""
        if instant is None
        else timezone.localtime(instant).strftime("%Y-%m-%d %H:%M")
    )


def _flag(value: bool | None) -> str:
    return "" if value is None else str(int(value))


@operation(
    "attendance.record.export",
    kind="query",
    permission="attendance.clock",
    input=RecordExportIn,
    output=ExportOut,
    expose_api=True,
    ai={
        "description": "Exports the working days of the filter (every page) as a CSV for the accountant or a "
        "labour inspection: date, person, clock-in, clock-out, break and worked minutes, status and "
        "whether it was clocked within the workplace radius. An employee exports only their own."
    },
)
def export_records(ctx: OperationContext, params: RecordExportIn) -> dict:
    as_of = timezone.now()
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    count = 0
    hours = review_hours()
    for record in scoped_records(ctx, params, as_of, hours):
        breaks, worked = durations(record, as_of, hours)
        writer.writerow(
            [
                record.work_date.isoformat(),
                _cell(record.member_name),
                _local(record.clock_in_at),
                _local(record.clock_out_at),
                breaks // 60,
                "" if worked is None else worked // 60,
                effective_status(record, hours, as_of),
                _flag(record.in_within_radius),
                _flag(record.out_within_radius),
            ]
        )
        count += 1
    return {
        "filename": export_filename(params.date_from, params.date_to),
        "content_type": "text/csv",
        "rows": count,
        "csv": buffer.getvalue(),
    }


@operation(
    "attendance.correction.list",
    kind="query",
    permission="attendance.clock",
    input=CorrectionListIn,
    output=CorrectionPage,
    expose_api=True,
    ai={
        "description": "The history of corrections of a working day (or of all of them): the times before "
        "and after, the reason, who and when, newest first. An employee sees the history of their own days."
    },
)
def list_corrections(ctx: OperationContext, params: CorrectionListIn) -> dict:
    trails = Correction.objects.all()
    if params.record_id is not None:
        trails = trails.filter(record=visible_record(ctx, params.record_id))
    elif not ctx.has(VIEW_ALL):
        own = _own_days(ctx)
        trails = (
            trails.filter(record__in=Record.objects.filter(own))
            if own is not None
            else trails.none()
        )
    trails = trails.order_by("-created_at", "-id")
    rows = [
        correction_out(t) for t in trails[params.offset : params.offset + params.limit]
    ]
    return _page(rows, trails.count(), params)


@operation(
    "attendance.presence.list",
    kind="query",
    permission=VIEW_ALL,
    input=PresenceListIn,
    output=PresencePage,
    expose_api=True,
    ai={
        "description": "Who is clocked in right now («who is in?»): how many and who, since when and whether "
        "they are on a break. A day waiting for review does not count."
    },
)
def list_presence(ctx: OperationContext, params: PresenceListIn) -> dict:
    # Who is in: an open day within the review hours (a forgotten one is not), of a record that is not
    # terminated (its person no longer works here).
    limit = timezone.now() - dt.timedelta(hours=review_hours())
    records = annotated(
        Record.objects.filter(status=Record.Status.OPEN, clock_in_at__gte=limit).exclude(
            member__status=Member.Status.TERMINATED
        )
    )
    if params.search:
        records = records.filter(member_name__icontains=params.search)
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
    "attendance.person.list",
    kind="query",
    permission=VIEW_ALL,
    input=PersonListIn,
    output=PersonPage,
    expose_api=True,
    ai={
        "description": "The people whose working days can be listed: every staff record that is not "
        "terminated, and the terminated ones that have days (kept four years). Search by name."
    },
)
def list_people(ctx: OperationContext, params: PersonListIn) -> dict:
    with_days = Record.objects.filter(member=OuterRef("pk"))
    people = (
        Member.objects.annotate(name=member_name_expression())
        .filter(
            ~Q(status=Member.Status.TERMINATED) | Q(pk__in=with_days.values("member"))
        )
        .order_by("first_name", "last_name", "id")
    )
    if params.search:
        people = people.filter(name__icontains=params.search)
    rows = [
        {"id": m.id, "name": m.name, "status": m.status}
        for m in people[params.offset : params.offset + params.limit]
    ]
    return _page(rows, people.count(), params)


@operation(
    "attendance.settings.get",
    kind="query",
    permission="attendance.clock",
    input=EmptyIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "description": "The time clock settings: whether a personal device must share its location and be "
        "within the workplace radius to clock in, the radius, the workplace and after how many hours a "
        "forgotten day is flagged for review."
    },
)
def get_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_values(saved_settings())
