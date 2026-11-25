"""The intervals of a day, and the one check of a set of them (``check_intervals``) every form applies."""

import datetime as dt
from typing import Any

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import ValidationInfo, field_validator

from apps.schedule.engine import MAX_INTERVALS, Interval, IntervalError, normalize
from apps.schedule.schemas.fields import D_INTERVALS, T_INTERVALS

MISSING_HOURS = _("An open day needs at least one opening interval.")
EMPTY_INTERVAL = _(
    "An interval cannot open and close at the same time; 00:00–00:00 is open 24 hours."
)
OVERLAPPING = _(
    "Two intervals overlap (or one runs past midnight into another); adjust the times so they do not clash."
)
TOO_MANY = _("At most 12 intervals a day.")
_INTERVAL_MESSAGES = {
    "empty": EMPTY_INTERVAL,
    "overlapping": OVERLAPPING,
    "too_many": TOO_MANY,
}


class IntervalIn(Schema):
    open_time: dt.time = Field(
        description="Opening time, HH:MM on the business's clock."
    )
    close_time: dt.time = Field(
        description="Closing time, HH:MM. Earlier than (or equal to) the opening crosses midnight (22:00–02:00); "
        "00:00–00:00 is open 24 hours."
    )


class IntervalOut(Schema):
    open_time: dt.time = Field(description="Opening time on the business's clock.")
    close_time: dt.time = Field(
        description="Closing time; at or before the opening it crosses midnight."
    )


def check_intervals(is_closed: bool, intervals: list[IntervalIn]) -> list[IntervalIn]:
    """The intervals as stored: none when closed; else sorted, without seconds, or ``ValueError``."""
    if is_closed:
        return []
    if not intervals:
        raise ValueError(str(MISSING_HOURS))
    try:
        checked = normalize(Interval(i.open_time, i.close_time) for i in intervals)
    except IntervalError as refused:
        raise ValueError(str(_INTERVAL_MESSAGES[refused.code])) from None
    return [IntervalIn(open_time=i.open_time, close_time=i.close_time) for i in checked]


def _intervals_field(**options: Any) -> Any:
    return Field(
        default_factory=list,
        max_length=MAX_INTERVALS,
        validate_default=True,
        title=T_INTERVALS,
        description=D_INTERVALS,
        **options,
    )


class _CheckedIntervals:
    """``intervals`` checked against ``is_closed`` (declared before it) with ``check_intervals``."""

    @field_validator("intervals", check_fields=False)
    @classmethod
    def _checked(
        cls, intervals: list[IntervalIn], info: ValidationInfo
    ) -> list[IntervalIn]:
        if "is_closed" not in info.data:
            return intervals
        return check_intervals(info.data["is_closed"], intervals)
