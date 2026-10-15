"""Input and output schemas of the schedule app's operations (OpenAPI, live params, 422 per field, and the
JSON Schema of the assistant's tools: every field says what it is).

The rules of a set of intervals live once, in ``check_intervals`` (engine.py underneath): the weekly day,
the special day and the temporary change refuse the same things with the same words, under
``intervals``. A day of the week is a number (0 = Monday) or its name in English or Spanish, so the
assistant can be spoken to.
"""

import datetime as dt
import unicodedata
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import (
    BeforeValidator,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
)

from apps.schedule.engine import (
    MAX_INTERVALS,
    Interval,
    IntervalError,
    normalize,
    parse_when,
)

T = TypeVar("T")

MISSING_HOURS = _("An open day needs at least one opening interval.")
EMPTY_INTERVAL = _(
    "An interval cannot open and close at the same time; 00:00–00:00 is open 24 hours."
)
OVERLAPPING = _(
    "Two intervals overlap (or one runs past midnight into another); adjust the times so they do not clash."
)
TOO_MANY = _("At most 12 intervals a day.")
RANGE_BACKWARDS = _("The end date cannot be before the start date.")
RANGE_TOO_LONG = _("At most 366 days at once.")
WHICH_SPECIAL_DAY = _("Say which special day: its id, its name or its date.")
WHICH_OVERRIDE = _(
    "Say which temporary change: its id, its reason or a date it covers."
)
INVALID_MOMENT = _("That date and time are not valid.")
OUT_OF_CALENDAR = _("Choose a date between 1900 and 2200.")

_INTERVAL_MESSAGES = {
    "empty": EMPTY_INTERVAL,
    "overlapping": OVERLAPPING,
    "too_many": TOO_MANY,
}
MAX_RANGE_DAYS = 366
MAX_BULK = 366
#: Intervals a day of the bulk may carry before the whole list is refused (the cap of a day is 12).
MAX_BULK_INTERVALS = 100
#: The days «is it open?» and the hours of a range answer for: far beyond any booking, and far from the
#: ends of Python's calendar (year 1, year 9999), where a day more or an hour of offset overflows.
MIN_DATE = dt.date(1900, 1, 1)
MAX_DATE = dt.date(2200, 12, 31)

Direction = Literal["asc", "desc"]
Source = Literal["special_day", "override", "weekly", "none"]
Code = Literal[
    "exception_closed",
    "exception_hours",
    "open_interval",
    "closed_today",
    "overnight_open",
    "outside_hours",
    "no_hours",
]

# Descriptions shared by several schemas.
D_IS_CLOSED = (
    "True: closed all day (its intervals are ignored). False: open in its intervals."
)
D_INTERVALS = (
    "The opening intervals, one per stretch (a split shift is two: 10:00–14:00 and 17:00–20:00); at most 12, "
    "in any order. Required when it is open."
)
D_SEARCH = "Free text to search."
D_DIRECTION = "Sort direction: asc or desc."
D_SPECIAL_DAY_ID = (
    "The id of the special day; or say it by name or date in special_day."
)
D_SPECIAL_DAY_REF = "The special day by its name (Christmas) or its date (YYYY-MM-DD), when the id is not given."
D_OVERRIDE_ID = (
    "The id of the temporary change; or say it by reason or date in override."
)
D_OVERRIDE_REF = "The temporary change by its reason (Summer hours) or a date it covers (YYYY-MM-DD), when the id is not given."

# ── A day of the week, by number or by name ───────────────────────────────────────────────────

_WEEKDAY_NAMES = {
    0: ("monday", "mon", "lunes", "lun"),
    1: ("tuesday", "tue", "martes", "mar"),
    2: ("wednesday", "wed", "miercoles", "mie"),
    3: ("thursday", "thu", "jueves", "jue"),
    4: ("friday", "fri", "viernes", "vie"),
    5: ("saturday", "sat", "sabado", "sab"),
    6: ("sunday", "sun", "domingo", "dom"),
}
_BY_NAME = {
    name: weekday for weekday, names in _WEEKDAY_NAMES.items() for name in names
}


def _plain(text: str) -> str:
    """Lowercase, without accents or spaces at the ends («Miércoles» → «miercoles»)."""
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _weekday(value: Any) -> Any:
    if isinstance(value, str) and _plain(value) in _BY_NAME:
        return _BY_NAME[_plain(value)]
    return value


Weekday = Annotated[int, BeforeValidator(_weekday), Field(ge=0, le=6)]
Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
Search = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Reference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]

# ── Intervals ──────────────────────────────────────────────────────────────────────────────────


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


# ── Pages ──────────────────────────────────────────────────────────────────────────────────────


class PageIn(Schema):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(
        50, ge=1, le=100, description="How many rows to return (1 to 100)."
    )
    offset: int = Field(
        0, ge=0, description="How many rows to skip, for the next pages."
    )


class Page(Schema, Generic[T]):
    rows: list[T]
    total: int = Field(description="Rows that match, over all pages.")
    limit: int
    offset: int


class NoParamsIn(Schema):
    model_config = ConfigDict(extra="forbid")


class DeletedOut(Schema):
    id: UUID


def _not_before(field: str) -> Any:
    """A ``…_to`` / ``end_date`` field that may not come before ``field``."""

    def check(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get(field)
        if value is not None and start is not None and value < start:
            raise ValueError(str(RANGE_BACKWARDS))
        return value

    return classmethod(check)


def _in_calendar(day: dt.date | None) -> dt.date | None:
    """A day between ``MIN_DATE`` and ``MAX_DATE``, or ``ValueError`` (a 422 under the field)."""
    if day is not None and not MIN_DATE <= day <= MAX_DATE:
        raise ValueError(str(OUT_OF_CALENDAR))
    return day


def _out_of_calendar_text(text: str | None) -> bool:
    """A moment whose own date (as written) already lies out of ``MIN_DATE`` … ``MAX_DATE``."""
    try:
        return not MIN_DATE <= dt.date.fromisoformat((text or "").strip()[:10]) <= MAX_DATE
    except ValueError:
        return False


# ── The week ───────────────────────────────────────────────────────────────────────────────────


class WeekDayOut(Schema):
    weekday: int = Field(description="0 = Monday … 6 = Sunday.")
    name: str = Field(description="The day's name in the reader's language.")
    id: UUID | None = Field(
        description="The row of the day; null when the day is not set."
    )
    is_set: bool = Field(
        description="False: nothing configured for that day (not open, not closed)."
    )
    is_closed: bool
    intervals: list[IntervalOut]


class WeekOut(Schema):
    week_starts_on: int = Field(
        description="1 = Monday … 7 = Sunday: the order of ``days``."
    )
    confirmed: bool = Field(
        description="False while the week is the default one nobody has saved or confirmed."
    )
    timezone: str = Field(
        description="The business's time zone (IANA), the clock the hours are read with."
    )
    days: list[WeekDayOut] = Field(
        description="The seven days, from the one the week starts on."
    )


class SetDayIn(_CheckedIntervals, Schema):
    model_config = ConfigDict(extra="forbid")

    weekday: Weekday = Field(
        description="The day of the week: 0 = Monday … 6 = Sunday, or its name (monday, lunes)."
    )
    is_closed: bool = Field(False, description=D_IS_CLOSED)
    intervals: list[IntervalIn] = _intervals_field()


# ── Special days ───────────────────────────────────────────────────────────────────────────────


class SpecialDayOut(Schema):
    id: UUID
    date: dt.date
    name: str
    is_closed: bool
    recurring_yearly: bool
    notes: str
    intervals: list[IntervalOut]


SpecialDayPage = Page[SpecialDayOut]


class SpecialDayFields(Schema):
    """A special day as the bulk takes it: the rules of its intervals are checked day by day."""

    model_config = ConfigDict(extra="forbid")

    date: dt.date = Field(description="The date, YYYY-MM-DD (a real calendar date).")
    name: Name = Field(description="Its name (Christmas, Local holiday).")
    is_closed: bool = Field(True, description=D_IS_CLOSED + " Closed by default.")
    # The bulk checks the 12-interval cap day by day (a day over it is skipped, `invalid_hours`); this
    # bound only stops an absurd payload, refused whole.
    intervals: list[IntervalIn] = Field(
        default_factory=list, max_length=MAX_BULK_INTERVALS, description=D_INTERVALS
    )
    recurring_yearly: bool = Field(
        False,
        description="True: it repeats on the same day and month every year (also the years before).",
    )
    notes: Notes = Field("", description="Optional notes.")


class SpecialDayIn(_CheckedIntervals, SpecialDayFields):
    intervals: list[IntervalIn] = _intervals_field()


class SpecialDayRefIn(Schema):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = Field(None, description=D_SPECIAL_DAY_ID)
    special_day: Reference | None = Field(
        None, validate_default=True, description=D_SPECIAL_DAY_REF
    )

    @field_validator("special_day")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None and "id" in info.data and info.data["id"] is None:
            raise ValueError(str(WHICH_SPECIAL_DAY))
        return value


class SpecialDayPatchIn(SpecialDayRefIn):
    """Only what is sent changes; sent intervals replace them all."""

    date: dt.date | None = Field(None, description="The new date, YYYY-MM-DD.")
    name: Name | None = Field(None, description="The new name.")
    is_closed: bool | None = Field(None, description=D_IS_CLOSED)
    intervals: list[IntervalIn] | None = Field(
        None, max_length=MAX_INTERVALS, description=D_INTERVALS
    )
    recurring_yearly: bool | None = Field(
        None, description="True: it repeats on the same day and month every year."
    )
    notes: Notes | None = Field(None, description="The new notes.")


class BulkSpecialDayIn(Schema):
    model_config = ConfigDict(extra="forbid")

    special_days: list[SpecialDayFields] = Field(
        min_length=1,
        max_length=MAX_BULK,
        description="The special days to create, 1 to 366.",
    )


class BulkSkippedOut(Schema):
    index: int = Field(description="Position of the day in the list sent, from 0.")
    date: dt.date
    code: Literal["already_exists", "invalid_hours"] = Field(
        description="Why it was skipped."
    )
    message: str = Field(description="The reason, in the reader's language.")


class BulkCreatedOut(Schema):
    created: list[UUID] = Field(
        description="The ids of the special days created, in the order sent."
    )
    skipped: list[BulkSkippedOut] = Field(
        description="The days that were not created, with their reason."
    )


class SpecialDayListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH + " Name or notes.")
    date_from: dt.date | None = Field(
        None, description="Only the special days on or after this date."
    )
    date_to: dt.date | None = Field(
        None, description="Only the special days on or before this date."
    )
    name: Search | None = Field(
        None, description="Only the special days whose name contains this."
    )
    is_closed: bool | None = Field(
        None, description="True: only the closed ones; false: only the open ones."
    )
    recurring_yearly: bool | None = Field(
        None, description="True: only the yearly ones; false: only the one-off ones."
    )
    sort: Literal["date", "name", "is_closed", "recurring_yearly", "id"] = Field(
        "date", description="Column to sort by."
    )
    dir: Direction = Field("asc", description=D_DIRECTION)

    _date_to = field_validator("date_to")(_not_before("date_from"))


# ── Temporary changes ──────────────────────────────────────────────────────────────────────────


class OverrideOut(Schema):
    id: UUID
    start_date: dt.date
    end_date: dt.date
    reason: str
    is_closed: bool
    intervals: list[IntervalOut]


OverridePage = Page[OverrideOut]


class OverrideIn(_CheckedIntervals, Schema):
    model_config = ConfigDict(extra="forbid")

    start_date: dt.date = Field(
        description="First day it applies, YYYY-MM-DD (included)."
    )
    end_date: dt.date = Field(
        description="Last day it applies, YYYY-MM-DD (included); the same date for one day."
    )
    reason: Name = Field(description="Why (Holidays, Summer hours, Works).")
    is_closed: bool = Field(True, description=D_IS_CLOSED + " Closed by default.")
    intervals: list[IntervalIn] = _intervals_field()

    _end_date = field_validator("end_date")(_not_before("start_date"))


class OverrideRefIn(Schema):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = Field(None, description=D_OVERRIDE_ID)
    override: Reference | None = Field(
        None, validate_default=True, description=D_OVERRIDE_REF
    )

    @field_validator("override")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None and "id" in info.data and info.data["id"] is None:
            raise ValueError(str(WHICH_OVERRIDE))
        return value


class OverridePatchIn(OverrideRefIn):
    """Only what is sent changes; sent intervals replace them all."""

    start_date: dt.date | None = Field(
        None, description="The new first day, YYYY-MM-DD."
    )
    end_date: dt.date | None = Field(None, description="The new last day, YYYY-MM-DD.")
    reason: Name | None = Field(None, description="The new reason.")
    is_closed: bool | None = Field(None, description=D_IS_CLOSED)
    intervals: list[IntervalIn] | None = Field(
        None, max_length=MAX_INTERVALS, description=D_INTERVALS
    )


class OverrideListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH + " Reason.")
    start_from: dt.date | None = Field(
        None, description="Only the changes starting on or after this date."
    )
    start_to: dt.date | None = Field(
        None, description="Only the changes starting on or before this date."
    )
    end_from: dt.date | None = Field(
        None, description="Only the changes ending on or after this date."
    )
    end_to: dt.date | None = Field(
        None, description="Only the changes ending on or before this date."
    )
    reason: Search | None = Field(
        None, description="Only the changes whose reason contains this."
    )
    is_closed: bool | None = Field(
        None, description="True: only the closed ones; false: only the open ones."
    )
    sort: Literal["start_date", "end_date", "reason", "is_closed", "id"] = Field(
        "start_date", description="Column to sort by."
    )
    dir: Direction = Field("asc", description=D_DIRECTION)

    _start_to = field_validator("start_to")(_not_before("start_from"))
    _end_to = field_validator("end_to")(_not_before("end_from"))


# ── Settings ───────────────────────────────────────────────────────────────────────────────────


class SettingsOut(Schema):
    week_starts_on: int = Field(description="1 = Monday … 7 = Sunday.")
    hours_confirmed: bool = Field(
        description="Somebody saved a day or confirmed the week."
    )
    timezone: str = Field(
        description="The business's time zone (IANA): the clock the hours are read with."
    )


class SettingsIn(Schema):
    model_config = ConfigDict(extra="forbid")

    week_starts_on: int | None = Field(
        None,
        ge=1,
        le=7,
        description="The day the week's table starts on: 1 = Monday … 7 = Sunday.",
    )


# ── Is it open? ────────────────────────────────────────────────────────────────────────────────


class IsOpenIn(Schema):
    model_config = ConfigDict(extra="forbid")

    when: str | None = Field(
        None,
        max_length=40,
        description="The moment: an instant with its offset (2026-08-18T08:00:00Z), converted to the business's "
        "clock; or the shop's own wall clock without offset (2026-08-18T10:00 — «tomorrow at ten» is written so). "
        "Empty: now. Between 1900 and 2200.",
    )

    @field_validator("when")
    @classmethod
    def _a_moment(cls, value: str | None) -> str | None:
        try:
            moment = parse_when(value, ZoneInfo("UTC"), dt.datetime.now(dt.UTC))
        except ValueError:
            # A moment that converts out of the calendar (year 1 or 9999 with an offset) is out of it too.
            if _out_of_calendar_text(value):
                raise ValueError(str(OUT_OF_CALENDAR)) from None
            raise ValueError(str(INVALID_MOMENT)) from None
        _in_calendar(moment.date())
        return value


class IsOpenOut(Schema):
    is_open: bool
    code: Code = Field(
        description="Why, as a stable code the caller phrases in its own language."
    )
    source: Source = Field(
        description="Which rule decided: special_day, override, weekly or none."
    )
    rule_id: UUID | None = Field(
        description="The row that decided (null with no rule)."
    )
    intervals: list[str] = Field(
        description="The intervals that explain it, HH:MM–HH:MM."
    )
    timezone: str
    today: dt.date = Field(description="The business's date of the moment.")
    current_time: str = Field(description="The business's time of the moment, HH:MM.")
    reason: str | None = Field(
        description="The name of the special day or the reason of the change that decided."
    )


# ── The hours of a range of days (for the appointment book) ───────────────────────────────────


class HoursRangeIn(Schema):
    model_config = ConfigDict(extra="forbid")

    date_from: dt.date = Field(
        description="First day, YYYY-MM-DD, on the business's calendar (between 1900 and 2200)."
    )
    date_to: dt.date | None = Field(
        None,
        validate_default=True,
        description="Last day, YYYY-MM-DD (included); empty = the first day alone.",
    )

    @field_validator("date_from")
    @classmethod
    def _from_in_calendar(cls, value: dt.date) -> dt.date:
        return _in_calendar(value)

    @field_validator("date_to")
    @classmethod
    def _range(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        _in_calendar(value)
        start = info.data.get("date_from")
        if start is None:
            return value
        end = value or start
        if end < start:
            raise ValueError(str(RANGE_BACKWARDS))
        if (end - start).days >= MAX_RANGE_DAYS:
            raise ValueError(str(RANGE_TOO_LONG))
        return end


class SpanOut(Schema):
    start: dt.datetime = Field(
        description="Opening, the business's wall-clock date and time."
    )
    end: dt.datetime = Field(
        description="Closing (excluded); the next day when it crosses midnight."
    )


class DayHoursOut(Schema):
    date: dt.date
    source: Source = Field(
        description="Which rule governs the day: special_day, override, weekly or none."
    )
    rule_id: UUID | None
    name: str = Field(
        description="The special day's name or the change's reason; empty for the week."
    )
    is_closed: bool
    intervals: list[IntervalOut]
    spans: list[SpanOut] = Field(
        description="The intervals as wall-clock date and time; a booking fits inside one."
    )


class HoursRangeOut(Schema):
    timezone: str
    days: list[DayHoursOut]
