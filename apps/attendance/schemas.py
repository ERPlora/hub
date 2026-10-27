"""Input and output schemas of the attendance app's operations (OpenAPI, live params, 422 per field, and
the assistant's tools: every input field carries a ``description``).

Cross-field rules are field validators on the later field (``info.data`` holds the earlier ones), so a
422 names the field to fix. A person is named by id or by name, because the assistant speaks names;
none of the two means the caller. Times travel as ISO 8601: with an offset they are that instant;
without one they are the business's wall clock (phase 1, ``settings.TIME_ZONE``). Durations are seconds.
"""

import datetime as dt
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import AfterValidator, StringConstraints, ValidationInfo, field_validator

T = TypeVar("T")

# Validation messages (English source, Spanish in locale/).
OUT_BEFORE_IN = _("The clock-out must be after the clock-in.")
BOTH_COORDINATES = _("Send both the latitude and the longitude, or neither.")
DATES_ORDER = _("The end date cannot be before the start date.")

RecordStatus = Literal["open", "closed", "needs_review"]
Source = Literal["shared", "personal"]
Radius = Literal[50, 100, 250, 500, 1000]

# The columns the list sorts by, both ways ("-" first = descending); id is always the tie-break.
RECORD_SORTS = (
    "work_date",
    "clock_in_at",
    "clock_out_at",
    "status",
    "member_name",
    "id",
)
RecordSort = Literal[
    tuple(f"{sign}{key}" for key in RECORD_SORTS for sign in ("", "-"))
]


def _text(max_length: int, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


def _business_time(value: dt.datetime) -> dt.datetime:
    """An instant: a time without offset is read on the business's wall clock."""
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_default_timezone())
    return value


MemberName = _text(200, 1)
Search = _text(100)
Reason = _text(500, 3)
Instant = Annotated[dt.datetime, AfterValidator(_business_time)]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
Accuracy = Annotated[float, Field(ge=0, le=100_000)]

# Field descriptions shared by several schemas (the assistant reads them).
D_MEMBER_ID = (
    "Id of the staff member to act on. Leave it and `member` empty to act on yourself (your own staff "
    "record); acting on someone else needs the permission to clock others."
)
D_MEMBER = "Name of the staff member to act on (first name, full name or part of it) when the id is not known."
D_LAT = (
    "Latitude of the device at this moment (WGS-84), only when it shares its location."
)
D_LNG = (
    "Longitude of the device at this moment (WGS-84), only when it shares its location."
)
D_ACCURACY = "Accuracy of that position, in metres, as the device reports it."
D_SEARCH_PEOPLE = "Text to look for in the person's name."


class PageIn(Schema):
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


class EmptyIn(Schema):
    pass


class RecordRefIn(Schema):
    id: UUID = Field(description="The working day's id.")


class TerminatedIn(Schema):
    """The payload of ``staff.member.terminated``."""

    id: UUID = Field(description="Id of the staff member who was terminated.")


# A person (none = the caller), and where the device is


class MemberRefIn(Schema):
    member_id: UUID | None = Field(None, description=D_MEMBER_ID)
    member: MemberName | None = Field(None, description=D_MEMBER)


class PositionIn(MemberRefIn):
    # Titles: the names the assistant's card gives these data, the Settings screen's («Latitude», «Longitude»).
    lat: Latitude | None = Field(None, title=gettext_noop("Latitude"), description=D_LAT)
    lng: Longitude | None = Field(
        None, title=gettext_noop("Longitude"), description=D_LNG, validate_default=True
    )
    accuracy_m: Accuracy | None = Field(
        None, title=gettext_noop("Accuracy (m)"), description=D_ACCURACY
    )

    @field_validator("lng")
    @classmethod
    def _both(cls, value: float | None, info: ValidationInfo) -> float | None:
        if "lat" in info.data and (info.data["lat"] is None) != (value is None):
            raise ValueError(str(BOTH_COORDINATES))
        return value


class ClockInIn(PositionIn):
    """Clock in. Whether the device is the counter POS or someone's own phone is not the caller's to
    declare: the Hub knows it from the session's device (phase 2; until then, the shared one)."""


class ClockOutIn(PositionIn):
    pass


class BreakIn(MemberRefIn):
    pass


class CorrectIn(Schema):
    record_id: UUID = Field(description="Id of the working day to correct.")
    clock_in_at: Instant = Field(
        description="The right clock-in, ISO 8601. Without an offset it is the business's local time."
    )
    clock_out_at: Instant | None = Field(
        None,
        validate_default=True,
        description="The right clock-out, after the clock-in; empty to leave the day open again.",
    )
    reason: Reason = Field(
        description="Why the day is corrected (3 to 500 characters). Mandatory: it stays in the day's "
        "history and is what an inspector reads."
    )

    @field_validator("clock_out_at")
    @classmethod
    def _after(
        cls, value: dt.datetime | None, info: ValidationInfo
    ) -> dt.datetime | None:
        start = info.data.get("clock_in_at")
        if value is not None and start is not None and value <= start:
            raise ValueError(str(OUT_BEFORE_IN))
        return value


class SettingsIn(Schema):
    """Only the fields sent change; a coordinate sent empty clears the workplace."""

    require_location: bool | None = Field(
        None,
        description="Require the location when clocking in from a personal device (never on the counter POS).",
    )
    geofence_radius_m: Radius | None = Field(
        None,
        description="How far from the workplace a personal device may clock in: 50, 100, 250, 500 or 1000 m.",
    )
    workplace_lat: Latitude | None = Field(
        None, description="Latitude of the workplace; empty to clear it."
    )
    workplace_lng: Longitude | None = Field(
        None, description="Longitude of the workplace; empty to clear it."
    )
    auto_close_after_hours: int | None = Field(
        None,
        ge=1,
        le=24,
        strict=True,
        description="A day still open after this many hours (1 to 24) is flagged for review.",
    )


# Lists


class RecordListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH_PEOPLE)
    member_id: UUID | None = Field(
        None, description="Keep the days of this staff member (by id)."
    )
    member: MemberName | None = Field(
        None, description="Keep the days of this staff member (by name)."
    )
    mine: bool = Field(False, description="Keep only your own days.")
    status: RecordStatus | None = Field(
        None,
        description="Keep the days in this status: open, closed or needs_review (forgotten clock-out).",
    )
    date_from: dt.date | None = Field(
        None, description="Keep the days from this business date on (YYYY-MM-DD)."
    )
    date_to: dt.date | None = Field(
        None,
        validate_default=True,
        description="Keep the days up to this business date (YYYY-MM-DD).",
    )
    sort: RecordSort = Field(
        "-clock_in_at", description="Column to sort by; a leading «-» sorts descending."
    )

    @field_validator("date_to")
    @classmethod
    def _in_order(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("date_from")
        if value is not None and start is not None and value < start:
            raise ValueError(str(DATES_ORDER))
        return value


class RecordExportIn(RecordListIn):
    pass


class CorrectionListIn(PageIn):
    record_id: UUID | None = Field(
        None, description="Keep the corrections of this working day."
    )


class PresenceListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH_PEOPLE)


class PersonListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH_PEOPLE)


# Outputs


class MemberBriefOut(Schema):
    id: UUID
    name: str


class RecordOut(Schema):
    id: UUID
    member_id: UUID
    member_name: str
    work_date: dt.date = Field(description="The business day of the clock-in.")
    clock_in_at: dt.datetime
    clock_out_at: dt.datetime | None
    status: RecordStatus
    source: Source
    in_distance_m: float | None
    in_within_radius: bool | None
    out_distance_m: float | None
    out_within_radius: bool | None
    note: str
    break_count: int
    break_seconds: int = Field(
        description="Seconds of break as of `as_of` (the running one included)."
    )
    worked_seconds: int | None = Field(
        description="Seconds worked as of `as_of`, breaks taken off; empty for a day waiting for review."
    )
    break_started_at: dt.datetime | None = Field(
        description="Start of the break running now, if any."
    )
    correction_count: int
    as_of: dt.datetime


class BreakOut(Schema):
    id: UUID
    started_at: dt.datetime
    ended_at: dt.datetime | None
    seconds: int


class RecordDetailOut(RecordOut):
    in_lat: float | None
    in_lng: float | None
    in_accuracy_m: float | None
    out_lat: float | None
    out_lng: float | None
    out_accuracy_m: float | None
    created_by_name: str
    created_at: dt.datetime
    updated_at: dt.datetime
    breaks: list[BreakOut]


class TodayOut(Schema):
    date: dt.date
    worked_seconds: int
    break_seconds: int
    running: Literal["work", "break"] | None = Field(
        description="Which of today's totals is growing now."
    )


class CurrentOut(Schema):
    member: MemberBriefOut | None = Field(
        description="Your staff record; empty when your user is not linked to one."
    )
    open: RecordOut | None
    today: TodayOut
    recent: list[RecordOut]
    as_of: dt.datetime


class CorrectionOut(Schema):
    id: UUID
    record_id: UUID
    old_clock_in_at: dt.datetime
    old_clock_out_at: dt.datetime | None
    old_status: RecordStatus
    new_clock_in_at: dt.datetime
    new_clock_out_at: dt.datetime | None
    new_status: RecordStatus
    reason: str
    is_system: bool
    created_by_name: str
    created_at: dt.datetime


class PresenceOut(Schema):
    record_id: UUID
    member_id: UUID
    member_name: str
    clock_in_at: dt.datetime
    break_started_at: dt.datetime | None
    source: Source


class PersonOut(Schema):
    id: UUID
    name: str
    status: str = Field(
        description="The staff record's status (active, inactive, on_leave, terminated)."
    )


class ExportOut(Schema):
    filename: str
    content_type: str
    rows: int
    csv: str


class SettingsOut(Schema):
    require_location: bool
    geofence_radius_m: int
    workplace_lat: float | None
    workplace_lng: float | None
    auto_close_after_hours: int
    workplace_set: bool
    saved: bool = Field(
        description="Whether the business saved them; until then, the defaults."
    )
    updated_at: dt.datetime | None


class ReviewOut(Schema):
    flagged: int
    record_ids: list[UUID]


class ClosedOut(Schema):
    record: RecordOut | None


RecordPage = Page[RecordOut]
CorrectionPage = Page[CorrectionOut]
PresencePage = Page[PresenceOut]
PersonPage = Page[PersonOut]
