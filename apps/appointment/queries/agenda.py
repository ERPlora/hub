"""The agenda the rules (``engine``) judge, and what each verdict says."""

import datetime as dt
from dataclasses import replace

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext

from apps.appointment import engine
from apps.appointment.models import Appointment, BlockedTime, Settings
from apps.schedule.queries import hours_for_range
from apps.schedule.schemas import HoursRangeIn
from apps.staff.models import Member
from apps.staff.queries import member_availability
from apps.staff.schemas.availability import AvailabilityIn
from base.business import business_zone

from .business import current_settings, day_bounds, rules_of
from .reads import BUSY

#: Schedules answers at most 366 days at once, Staff 731.
HOURS_CHUNK = 366
STAFF_CHUNK = 731

#: Why a time cannot be booked (engine.CODES) → what the person reads.
VERDICTS = {
    "invalid_start": _("That start date and time is not valid."),
    "in_past": _("That time has already passed."),
    "too_soon": _("This appointment must be booked further in advance."),
    "too_far": _("This appointment cannot be booked that far in advance."),
    "outside_schedule": _("That time is outside the business's opening hours."),
    "outside_staff_hours": _(
        "That professional does not work at that time. Pick another time or another professional."
    ),
    "blocked": _("That time is blocked in the agenda."),
    "overlap": _(
        "That professional already has an appointment at that time. Pick another time or another professional."
    ),
    "service_unavailable": _("A service of this series can no longer be booked."),
}


def verdict_message(code: str) -> str:
    return str(VERDICTS.get(code, VERDICTS["invalid_start"]))


def reader(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to read the hours of Schedules and Staff (booking needs no right in those apps)."""
    return replace(ctx, permissions=ctx.permissions | {"schedule.view", "staff.view"})


def _chunks(date_from: dt.date, date_to: dt.date, size: int):
    start = date_from
    while start <= date_to:
        end = min(date_to, start + dt.timedelta(days=size - 1))
        yield start, end
        start = end + dt.timedelta(days=1)


def business_days(ctx: OperationContext, date_from: dt.date, date_to: dt.date) -> dict:
    """The business's hours of ``date_from - 1`` … ``date_to`` (the eve too: its overnight tail)."""
    out = {}
    for start, end in _chunks(date_from - dt.timedelta(days=1), date_to, HOURS_CHUNK):
        hours = hours_for_range(reader(ctx), HoursRangeIn(date_from=start, date_to=end))
        for day in hours.days:
            out[day.date] = engine.BusinessDay(
                day.date,
                restricted=day.source != "none",
                spans=tuple((span.start, span.end) for span in day.spans),
            )
    return out


def staff_days(
    ctx: OperationContext, member: Member, date_from: dt.date, date_to: dt.date
) -> dict:
    out = {}
    for start, end in _chunks(date_from, date_to, STAFF_CHUNK):
        answer = member_availability(
            reader(ctx),
            AvailabilityIn(member_id=member.id, date_from=start, date_to=end),
        )
        for day in answer.days:
            out[day.date] = engine.StaffDay(
                day.date,
                has_schedule=day.schedule_id is not None,
                available=tuple((span.start, span.end) for span in day.available),
                absences=tuple(
                    (None, None)
                    if absence.is_full_day
                    else (absence.start_time, absence.end_time)
                    for absence in day.time_off
                ),
            )
    return out


def load_agenda(  # noqa: PLR0913
    ctx: OperationContext,
    member: Member | None,
    date_from: dt.date,
    date_to: dt.date,
    *,
    exclude: tuple = (),
    settings: Settings | None = None,
) -> engine.Agenda:
    """Everything the rules need about ``member`` (or the business alone) from ``date_from`` to ``date_to``."""
    zone = business_zone()
    start, end = day_bounds(
        date_from - dt.timedelta(days=1), date_to + dt.timedelta(days=1)
    )
    blocks = BlockedTime.objects.filter(start__lt=end, end__gt=start)
    blocks = (
        blocks.filter(Q(staff__isnull=True) | Q(staff=member))
        if member
        else blocks.filter(staff__isnull=True)
    )
    busy = []
    if member is not None:
        busy = [
            engine.Period(
                item.start,
                item.end,
                id=item.id,
                label=f"{item.number} {item.customer_name}",
            )
            for item in Appointment.objects.filter(deleted_at__isnull=True)
            .filter(staff=member, status__in=BUSY, start__lt=end, end__gt=start)
            .exclude(pk__in=exclude)
            .order_by("start", "id")
        ]
    return engine.Agenda(
        zone=zone,
        rules=rules_of(settings or current_settings()),
        business=business_days(ctx, date_from, date_to),
        staff=staff_days(ctx, member, date_from, date_to) if member else None,
        blocks=[
            engine.Period(block.start, block.end, id=block.id, label=block.title)
            for block in blocks
        ],
        busy=busy,
    )


def conflicts_of(
    agenda: engine.Agenda, start: dt.datetime, end: dt.datetime
) -> list[dict]:
    rows = Appointment.objects.filter(
        deleted_at__isnull=True, pk__in=[period.id for period in engine.overlapping(agenda, start, end)]
    )
    zone = business_zone()
    return [
        {
            "id": item.id,
            "number": item.number,
            "customer_name": item.customer_name,
            "start": item.start.astimezone(zone),
            "end": item.end.astimezone(zone),
        }
        for item in rows.order_by("start", "id")
    ]
