"""When a staff member can work: the schedule that governs each day minus their approved time off (STAFF-F16)."""

import datetime as dt

from live.context import OperationContext
from live.operations import operation

from apps.staff.models import Schedule, TimeOff
from apps.staff.schemas.availability import AvailabilityIn, AvailabilityOut

from .reads import resolve_member


@operation(
    "staff.availability.for_member",
    kind="query",
    permission="staff.view",
    input=AvailabilityIn,
    output=AvailabilityOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "can Lucía work on Saturday afternoon?",
                "which days is Pablo free this month, counting his vacation?",
                "at what times can Ana see clients on Monday?",
            ),
            "es": (
                "¿Lucía puede trabajar el sábado por la tarde?",
                "¿qué días tiene libres Pablo este mes, contando sus vacaciones?",
                "¿a qué horas puede atender Ana el lunes?",
            ),
        },
        "description": "Returns when a staff member can work on each day of a date range: the shifts of "
        "the schedule that governs the day minus their approved time off. The authoritative answer to "
        "when a professional can work."
    },
)
def member_availability(ctx: OperationContext, data: AvailabilityIn) -> dict:
    """Per day: the governing schedule, its shifts, the approved absences and what is left (STAFF-F16).

    It knows nothing about appointments: it answers «when could this person work»; the caller
    intersects it with the rest. ``schedule_id`` null means no schedule governs that day.
    """
    member = resolve_member(data.member_id, data.member)
    schedules = list(
        Schedule.objects.filter(member=member, is_active=True).prefetch_related("days")
    )
    approved = list(
        TimeOff.objects.filter(
            member=member,
            status=TimeOff.Status.APPROVED,
            start_date__lte=data.date_to,
            end_date__gte=data.date_from,
        )
    )
    days = []
    for offset in range((data.date_to - data.date_from).days + 1):
        day = data.date_from + dt.timedelta(days=offset)
        schedule = governing_schedule(schedules, day)
        shifts = _shifts(schedule, day)
        absences = sorted(
            (
                absence
                for absence in approved
                if absence.start_date <= day <= absence.end_date
            ),
            key=lambda absence: (
                not absence.is_full_day,
                absence.start_time or dt.time.min,
                absence.id,
            ),
        )
        days.append(
            {
                "date": day,
                "schedule_id": schedule.id if schedule else None,
                "shifts": [{"start": start, "end": end} for start, end in shifts],
                "time_off": absences,
                "available": [
                    {"start": start, "end": end}
                    for start, end in _subtract(shifts, absences)
                ],
            }
        )
    return {"member_id": member.id, "days": days}


def governing_schedule(schedules: list[Schedule], day: dt.date) -> Schedule | None:
    """The active schedule that rules ``day``: a non-default one beats the default, then the latest
    «valid from», then the newest (STAFF-F13)."""
    valid = [
        schedule
        for schedule in schedules
        if (schedule.effective_from is None or schedule.effective_from <= day)
        and (schedule.effective_until is None or schedule.effective_until >= day)
    ]
    if not valid:
        return None
    return min(
        valid,
        key=lambda schedule: (
            schedule.is_default,
            schedule.effective_from is None,
            -(schedule.effective_from.toordinal() if schedule.effective_from else 0),
            -schedule.created_at.timestamp(),
            -schedule.id.int,
        ),
    )


def _shifts(schedule: Schedule | None, day: dt.date) -> list[tuple[dt.time, dt.time]]:
    """The working stretches of ``day`` under ``schedule``, split around the break; empty ones dropped."""
    if schedule is None:
        return []
    for working in schedule.days.all():
        if working.weekday == day.weekday():
            if working.break_start is None:
                pieces = [(working.start_time, working.end_time)]
            else:
                pieces = [
                    (working.start_time, working.break_start),
                    (working.break_end, working.end_time),
                ]
            return [(start, end) for start, end in pieces if start < end]
    return []


def _subtract(
    shifts: list[tuple[dt.time, dt.time]], absences: list[TimeOff]
) -> list[tuple[dt.time, dt.time]]:
    """``shifts`` minus the absences: a full day leaves nothing, a part day cuts its hours out.

    By hand: the only interval library of the right size (``portion``) is one person's project, and
    the ones that pass (``sympy``, ``pandas``) are far too big for this.
    """
    if any(absence.is_full_day for absence in absences):
        return []
    free = list(shifts)
    for absence in absences:
        remaining = []
        for start, end in free:
            if absence.end_time <= start or absence.start_time >= end:
                remaining.append((start, end))
                continue
            if start < absence.start_time:
                remaining.append((start, absence.start_time))
            if absence.end_time < end:
                remaining.append((absence.end_time, end))
        free = remaining
    return free
