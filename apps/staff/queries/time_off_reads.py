"""The time off of the live records, as its lists, the figures of the directory and the writes find it."""

import datetime as dt
from uuid import UUID

from django.db.models import Q, QuerySet, Value
from django.db.models.functions import Concat
from django.utils.translation import gettext_lazy as _

from apps.staff.models import Member, TimeOff

from .reads import TERMINATED

TIME_OFF_NOT_FOUND = _("That time-off request does not exist in this business.")

#: The time off that blocks a new request, and that Deactivate looks at.
LIVE_TIME_OFF = (TimeOff.Status.PENDING, TimeOff.Status.APPROVED)


def live_time_off() -> QuerySet[TimeOff]:
    """Time off of records that are not terminated, with ``member_name``."""
    return TimeOff.objects.exclude(member__status=TERMINATED).annotate(
        member_name=Concat("member__first_name", Value(" "), "member__last_name")
    )


def load_time_off(time_off_id: UUID) -> TimeOff | None:
    """A time off of a live record with its reason and its approver's name (a ``TimeOffDetailOut``)."""
    time_off = _with_approver(live_time_off().filter(pk=time_off_id)).first()
    if time_off is not None:
        _name_approvers([time_off])
    return time_off


def overlapping_time_off(  # noqa: PLR0913, PLR0917
    member: Member,
    start_date: dt.date,
    end_date: dt.date,
    start_time: dt.time | None,
    end_time: dt.time | None,
    statuses: tuple[str, ...] = LIVE_TIME_OFF,
    exclude_id: UUID | None = None,
) -> QuerySet[TimeOff]:
    """The member's time off in ``statuses`` that shares a day and, when both are part days, an hour.

    The same hours repeat on every day of a range, so two part days clash only if their hours do.
    """
    clashes = TimeOff.objects.filter(
        member=member,
        status__in=statuses,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if start_time is not None and end_time is not None:
        clashes = clashes.filter(
            Q(is_full_day=True) | Q(start_time__lt=end_time, end_time__gt=start_time)
        )
    if exclude_id is not None:
        clashes = clashes.exclude(pk=exclude_id)
    return clashes


def _away_on(day: dt.date) -> QuerySet[TimeOff]:
    return live_time_off().filter(
        status=TimeOff.Status.APPROVED, start_date__lte=day, end_date__gte=day
    )


def _with_approver(time_off: QuerySet[TimeOff]) -> QuerySet[TimeOff]:
    return time_off.select_related("approved_by")


def _name_approvers(rows: list[TimeOff]) -> None:
    for row in rows:
        person = row.approved_by
        row.approved_by_name = (person.name or person.username) if person is not None else None
