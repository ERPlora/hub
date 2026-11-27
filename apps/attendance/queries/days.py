"""A working day as the reads show it: the person's name, the breaks and the corrections, how long it was worked and
paused as of a moment, whether it is a forgotten one, and which days the caller may see."""

import datetime as dt
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
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import NotFound, PermissionDenied

from apps.attendance.models import Break, Correction, Record
from apps.attendance.schemas import RecordListIn
from base.ordering import list_order_for
from base.text_search import contains_text

from .people import actor_user, find_member
from .reads import READS_ANY_DAY, VIEW_ALL, _own_days, _reads_any, review_hours

RECORD_NOT_FOUND = _("That working day does not exist in this business.")
OWN_DAYS_ONLY = _("You can only see your own working days.")


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


def is_stale(record: Record, hours: int, now: dt.datetime) -> bool:
    """An open day older than ``hours``: a forgotten clock-out (ATTENDANCE-F05).

    It reads as waiting for review whether or not the worker's review (every quarter of an hour) has
    flagged it yet: it never counts «until now», and only a manager's correction closes it.
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
    """One day as services/ returns it after a write."""
    record = annotated(Record.objects.filter(pk=record_id)).get()
    return record_out(record, as_of or timezone.now(), review_hours())


def _owns(ctx: OperationContext, record: Record) -> bool:
    user = actor_user(ctx)
    return user is not None and record.member.user_id == user.pk


def visible_record(ctx: OperationContext, record_id: UUID) -> Record:
    """A day the caller may see (their own, or any for whoever sees the team or corrects); ``NotFound`` otherwise."""
    record = annotated(Record.objects.filter(pk=record_id)).first()
    if record is None or not (_reads_any(ctx, READS_ANY_DAY) or _owns(ctx, record)):
        raise NotFound(str(RECORD_NOT_FOUND))
    return record


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
        records = records.filter(contains_text(params.search, "member_name"))
    return records.order_by(*list_order_for(params.sort))
