"""What the writes of the hours share: the settings row, created by the first write and locked until the end of the
command, and the intervals a write stores: checked again against the rules, compared with what was there and
written in order."""

from collections.abc import Iterable
from typing import Any

from live.errors import InvalidPayload

from apps.schedule.models import Override, ScheduleSettings, SpecialDay
from apps.schedule.schemas.intervals import IntervalIn, check_intervals


def _locked_settings() -> ScheduleSettings:
    """The settings row, created by the first write, locked until the end of the command."""
    row = ScheduleSettings.objects.select_for_update().first()
    if row is None:
        ScheduleSettings.objects.get_or_create(slot=1)
        row = ScheduleSettings.objects.select_for_update().get(slot=1)
    return row


def _write_intervals(
    model: type, owner: dict[str, Any], intervals: Iterable[IntervalIn]
) -> None:
    """Replaces the intervals of their owner (``{"day": day}``…) with ``intervals``, in order."""
    model.objects.filter(**owner).delete()
    model.objects.bulk_create(
        model(
            **owner, position=position, open_time=i.open_time, close_time=i.close_time
        )
        for position, i in enumerate(intervals)
    )


def _checked(is_closed: bool, intervals: list[IntervalIn]) -> list[IntervalIn]:
    """``check_intervals`` with its refusal under ``intervals`` (a correction's merged values)."""
    try:
        return check_intervals(is_closed, intervals)
    except ValueError as refused:
        raise InvalidPayload(str(refused), fields={"intervals": str(refused)}) from None


def _stored(row: SpecialDay | Override) -> list[IntervalIn]:
    return [
        IntervalIn(open_time=i.open_time, close_time=i.close_time)
        for i in row.intervals.order_by("position")
    ]


def _same(left: list[IntervalIn], right: list[IntervalIn]) -> bool:
    return [(i.open_time, i.close_time) for i in left] == [
        (i.open_time, i.close_time) for i in right
    ]


def _apply_sent(row: SpecialDay | Override, sent: dict[str, Any]) -> bool:
    """Sets on ``row`` each sent value that changes it (``None`` changes nothing); whether any did."""
    changed = {field: value for field, value in sent.items() if value is not None and getattr(row, field) != value}
    for field, value in changed.items():
        setattr(row, field, value)
    return bool(changed)
