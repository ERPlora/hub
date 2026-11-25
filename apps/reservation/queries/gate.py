"""What the gate (engine.py) reads, shared with the writes (services/) inside the command's own transaction: the
book's rules, the slots of a day with what they hold, its blocks, its opening hours (Schedules) and a table's
facts (Tables).
"""

import datetime as dt
from dataclasses import replace
from uuid import UUID

from django.db.models import QuerySet
from live.context import OperationContext

from apps.reservation import engine
from apps.reservation.models import BlockedDate, Reservation, Settings, TimeSlot
from apps.reservation.queries.clock import wall_clock, window_of
from apps.schedule.queries import get_week, hours_for_range
from apps.schedule.schemas import HoursRangeIn, NoParamsIn
from apps.table.models import Table
from apps.table.queries import floor

S = Reservation.Status
#: What a slot counts (the old gate's rule): every reservation not cancelled nor a no-show.
UNCOUNTED = (S.CANCELLED, S.NO_SHOW)
#: What holds a table for its window: the ones still coming or sitting there.
HOLDING = (S.PENDING, S.CONFIRMED, S.SEATED)
#: The rules of Schedules a business sets on purpose (its usual week counts once confirmed).
EXCEPTIONS = frozenset({"special_day", "override"})


def current_settings() -> Settings:
    """The book's rules; the factory ones (unsaved) while nobody saved them."""
    return Settings.objects.first() or Settings()


def rules_of(settings: Settings) -> engine.Rules:
    return engine.Rules(
        min_party_size=settings.min_party_size,
        max_party_size=settings.max_party_size,
        min_advance_hours=settings.min_advance_hours,
        max_advance_days=settings.max_advance_days,
        require_phone=settings.require_phone,
        require_email=settings.require_email,
    )


def counted(day: dt.date, exclude: tuple = ()) -> QuerySet[Reservation]:
    """The reservations a day's slots count: live, not cancelled nor a no-show."""
    return (
        Reservation.objects.filter(is_deleted=False, date=day)
        .exclude(status__in=UNCOUNTED)
        .exclude(pk__in=exclude)
    )


def slots_of(day: dt.date, exclude: tuple = ()) -> list[engine.Slot]:
    """The slots of ``day``'s weekday, by start, with the reservations and guests they hold that day."""
    taken = list(counted(day, exclude).values("time", "party_size"))
    out = []
    for slot in TimeSlot.objects.filter(
        is_deleted=False, day_of_week=day.weekday()
    ).order_by("start_time", "id"):
        inside = [
            row for row in taken if slot.start_time <= row["time"] < slot.end_time
        ]
        out.append(
            engine.Slot(
                id=slot.pk,
                start=slot.start_time,
                end=slot.end_time,
                max_reservations=slot.max_reservations,
                max_covers=slot.max_covers,
                reserved=len(inside),
                covers=sum(row["party_size"] for row in inside),
            )
        )
    return out


def blocks_of(day: dt.date) -> list[BlockedDate]:
    return list(
        BlockedDate.objects.filter(is_deleted=False, date=day).order_by(
            "blocked_from", "id"
        )
    )


def engine_blocks(blocks: list[BlockedDate]) -> tuple[engine.Block, ...]:
    return tuple(
        engine.Block(block.is_full_day, block.blocked_from, block.blocked_until)
        for block in blocks
    )


def reader(ctx: OperationContext) -> OperationContext:
    """``ctx`` able to read the business's hours (booking needs no right in Schedules)."""
    return replace(ctx, permissions=ctx.permissions | {"schedule.view"})


def hours_of(ctx: OperationContext, day: dt.date) -> engine.Hours:
    """The business's opening spans of ``day`` and of its eve (past midnight), from Schedules.

    What governs a day: a special day or a temporary change always; the usual week only once the
    business saved or confirmed it — the default week Schedules ships with (Monday to Friday, 09:00 to
    18:00) is a suggestion, and would turn away every dinner of a restaurant that never opened Schedules.
    """
    confirmed = get_week(reader(ctx), NoParamsIn()).confirmed
    answer = hours_for_range(
        reader(ctx), HoursRangeIn(date_from=day - dt.timedelta(days=1), date_to=day)
    )

    def governs(entry) -> bool:
        return entry.source in EXCEPTIONS or (entry.source == "weekly" and confirmed)

    governed = [entry for entry in answer.days if governs(entry)]
    spans = [(span.start, span.end) for entry in governed for span in entry.spans]
    return engine.Hours(
        restricted=any(entry.date == day for entry in governed), spans=tuple(spans)
    )


def in_service(table: Table) -> bool:
    """A table may be booked: in use, not deleted, not blocked, and its zone (if any) in use."""
    if table.is_deleted or not table.is_active or table.blocked:
        return False
    return table.zone_id is None or (table.zone.is_active and not table.zone.is_deleted)


def booked_windows(
    table_id: UUID, window: engine.Window, exclude: tuple = ()
) -> list[tuple[Reservation, engine.Window]]:
    """The live reservations holding ``table_id`` around ``window`` (the days it touches and their
    neighbours), each with its window."""
    first = wall_clock(window.start).date()
    days = {first + dt.timedelta(days=offset) for offset in (-1, 0, 1)} | {
        wall_clock(window.end).date()
    }
    rows = (
        Reservation.objects.filter(
            is_deleted=False, table_id=table_id, status__in=HOLDING, date__in=days
        )
        .exclude(pk__in=exclude)
        .order_by("date", "time", "id")
    )
    out = []
    for row in rows:
        theirs = window_of(row.date, row.time, row.duration_minutes)
        if theirs.overlaps(window):
            out.append((row, theirs))
    return out


def table_facts(
    table: Table, window: engine.Window, exclude: tuple = ()
) -> engine.TableFacts:
    return engine.TableFacts(
        label=floor.table_label(table),
        in_service=in_service(table),
        booked=tuple(theirs for _, theirs in booked_windows(table.pk, window, exclude)),
    )
