"""The working day a command acts on: whose it is, the open one, the forgotten ones and the running break."""

import datetime as dt

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.outbox import record_event

from apps.attendance import events
from apps.attendance.models import Break, Record
from apps.attendance.queries.days import is_stale
from apps.attendance.queries.people import MEMBER_NOT_FOUND, clocked
from apps.attendance.queries.reads import review_hours
from apps.attendance.schemas import MemberRefIn
from apps.staff.models import Member

NOT_CLOCKED_IN = _("There is no open working day: clock in first.")
DAY_NEEDS_REVIEW = _(
    "This working day has been open more than %(hours)s hours and is waiting for review: a manager "
    "corrects it. Clock in to start a new day."
)

#: A clock-out never lands on its own clock-in (the database keeps «after»): the smallest step after it.
TICK = dt.timedelta(microseconds=1)


def _target(ctx: OperationContext, data: MemberRefIn) -> tuple[Member, bool]:
    """The staff record the command acts on (``clocked``), locked, and whether it is the caller's own. A record
    terminated meanwhile is ``NotFound``."""
    member, mine = clocked(ctx, data)
    locked = (
        Member.objects.select_for_update(no_key=True)
        .filter(pk=member.pk)
        .exclude(status=Member.Status.TERMINATED)
        .first()
    )
    if locked is None:
        raise NotFound(str(MEMBER_NOT_FOUND))
    return locked, mine


def _open_day(member: Member) -> Record | None:
    return Record.objects.filter(member=member, status=Record.Status.OPEN).first()


def _day_now(member: Member, now: dt.datetime) -> Record | None:
    """The person's open day to clock out of or pause; a forgotten one (past the review hours) is not.

    A forgotten day is never closed as a 20-hour day nor paused: 409 ``attendance.day_needs_review``,
    and a manager corrects it (ATTENDANCE-F05, F08). Clocking in again flags it and opens a new day.
    """
    record = _open_day(member)
    hours = review_hours()
    if record is not None and is_stale(record, hours, now):
        raise Conflict(
            str(DAY_NEEDS_REVIEW) % {"hours": hours}, code="attendance.day_needs_review"
        )
    return record


def _not_clocked_in() -> Conflict:
    return Conflict(str(NOT_CLOCKED_IN), code="attendance.not_clocked_in")


def _flag_stale(ctx: OperationContext, days, hours: int, now: dt.datetime) -> list:
    """ATTENDANCE-F05: the open days older than ``hours`` wait for review; nobody invents a clock-out."""
    flagged = []
    limit = now - dt.timedelta(hours=hours)
    for record in days.filter(
        status=Record.Status.OPEN, clock_in_at__lt=limit
    ).order_by("clock_in_at", "id"):
        # Only what is still open when the UPDATE runs: a clock-out meanwhile wins.
        updated = Record.objects.filter(pk=record.pk, status=Record.Status.OPEN).update(
            status=Record.Status.NEEDS_REVIEW, updated_at=now
        )
        if updated:
            record_event(
                ctx,
                events.RECORD_FLAGGED,
                {"id": str(record.id), "member_id": str(record.member_id)},
            )
            flagged.append(record.id)
    return flagged


def _end_break(ctx: OperationContext, record: Record, at: dt.datetime) -> bool:
    running = Break.objects.filter(record=record, ended_at__isnull=True).first()
    if running is None:
        return False
    running.ended_at = max(at, running.started_at)
    running.save(update_fields=["ended_at", "updated_at"])
    record_event(
        ctx,
        events.BREAK_ENDED,
        {
            "id": str(running.id),
            "record_id": str(record.id),
            "member_id": str(record.member_id),
        },
    )
    return True
