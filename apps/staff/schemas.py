"""Input and output schemas of the staff app's operations (OpenAPI, live params, 422 per field, and the
assistant's tools: every input field carries a ``description``).

Cross-field rules are field validators on the later field (``info.data`` holds the earlier ones), so
a 422 names the field to fix. Their messages are raised as text in the active language: the
request's, through ``LocaleMiddleware``. A staff member can be named by id or by name, because the
assistant speaks names; ``queries.resolve_member`` turns the name into the record.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import (
    AfterValidator,
    ConfigDict,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from base.schemas import names

T = TypeVar("T")

# Validation messages (English source, Spanish in locale/).
INVALID_EMAIL = _("Enter a valid email address.")
NO_MEMBER = _("Say which staff member: their id or their name.")
TIME_ORDER = _("The start time must be before the end time.")
BREAK_PAIR = _("The break needs a start and an end, or neither.")
BREAK_INSIDE = _("The break must fall inside the working hours.")
NO_DAYS = _("A schedule needs at least one working day with hours.")
WEEKDAY_REPEATED = _("Each weekday can appear only once.")
SCHEDULE_RANGE = _("The schedule's validity ends before it starts.")
END_BEFORE_START = _("The end date cannot be before the start date.")
PERIOD_BOTH_DAYS = _("A period of your own needs its first and its last day.")
RANGE_TOO_LONG = _("Ask for at most 731 days at a time.")
TIMES_REQUIRED = _("A half-day absence needs a start and an end time.")

#: The longest range staff.availability.for_member answers (two years and a day, as the old module).
MAX_AVAILABILITY_DAYS = 731
#: The most rows staff.member.bulk_create takes at once (the old module's batch).
MAX_BULK = 100
#: The largest role order the database column (a 4-byte integer) holds.
MAX_ORDER = 2_147_483_647

MemberStatus = Literal["active", "inactive", "on_leave"]
LeaveType = Literal["vacation", "sick", "personal", "training", "other"]
TimeOffStatus = Literal["pending", "approved", "rejected", "cancelled"]
#: A record's status as the commission report shows it: someone who left still earned what they sold.
RecordStatus = Literal["active", "inactive", "on_leave", "terminated"]
#: The commission report's periods, counted in business days up to today.
CommissionPeriod = Literal["today", "yesterday", "this_week", "this_month"]

# The columns each list sorts by, both ways ("-" first = descending); id is always the tie-break.
MEMBER_SORTS = (
    "name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "role_name",
    "status",
    "is_bookable",
    "hire_date",
    "color",
    "user_id",
    "id",
)
ROLE_SORTS = (
    "name",
    "description",
    "color",
    "order",
    "is_active",
    "member_count",
    "id",
)
TIME_OFF_SORTS = (
    "start_date",
    "end_date",
    "member_name",
    "leave_type",
    "status",
    "is_full_day",
    "approved_at",
    "id",
)


def _both_ways(keys: tuple[str, ...]):
    return Literal[tuple(f"{sign}{key}" for key in keys for sign in ("", "-"))]


MemberSort = _both_ways(MEMBER_SORTS)
RoleSort = _both_ways(ROLE_SORTS)
TimeOffSort = _both_ways(TIME_OFF_SORTS)


def _email(value: str) -> str:
    if value:
        try:
            validate_email(value)
        except DjangoValidationError:
            raise ValueError(str(INVALID_EMAIL)) from None
    return value


def _text(max_length: int, min_length: int = 0):
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=min_length, max_length=max_length
        ),
    ]


Name = _text(100, 1)
Text100 = _text(100)
Text500 = _text(500)
Text2000 = _text(2000)
Search = _text(100)
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254),
    AfterValidator(_email),
]
Phone = _text(20)
EmployeeNumber = _text(50)
# Empty, or #RRGGBB.
Color = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^(#[0-9A-Fa-f]{6})?$")
]
Cents = Annotated[int, Field(ge=0, le=99_999_999, json_schema_extra={"money": True})]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
BookingBuffer = Annotated[int, Field(ge=0, le=240)]
MemberName = _text(200, 1)

# Field descriptions shared by several schemas (the assistant reads them).
D_MEMBER_ID = "The staff member's id. Give it, or their name in `member`."
D_MEMBER = "The staff member's name (first name, full name or part of it) when the id is not known."
D_SEARCH_MEMBERS = (
    "Text to look for in the name, email, phone, employee number or role."
)
D_FIRST_NAME = "First name."
D_LAST_NAME = "Last name(s)."
D_EMAIL = "Email address; empty for none."
D_PHONE = "Phone number, as written; empty for none."
D_EMPLOYEE_NUMBER = "The business's own employee number; empty for none."
D_ROLE_ID = (
    "Id of the role (a catalogue label such as «stylist»; it grants no permission)."
)
D_ROLE = "Name of the role, when its id is not known (an active role of this business)."
#: A person of the business by their id in its database: the card names them (``base.hub_user.get``).
A_PERSON = names("base.hub_user.get")
D_USER_ID = "Id of the business user (account) the record hangs from; one user, one live record."
D_HIRE_DATE = "Hire date (YYYY-MM-DD)."
D_BOOKABLE = "Whether the person takes appointments."
D_BUFFER = "Minutes to leave between two appointments of this person (0 to 240)."
D_COLOR = "Colour of the person in the agenda, as #RRGGBB; empty for none."
D_SPECIALTIES = "Specialties, as free text."
D_BIO = "Short biography."
D_HOURLY_RATE = (
    "Hourly rate in cents: the minor unit of the business's currency (1250 = 12.50 in euros or złoty, ¥1,250 in yen). "
    "Needs the pay permission."
)
D_COMMISSION = "Commission as a percentage from 0 to 100, with up to two decimals. Needs the pay permission."
D_HR_NOTES = "Private HR notes; only shown with the pay. Needs the pay permission."


def _member_named(value: str | None, info: ValidationInfo, id_field: str) -> str | None:
    """``member`` is required when the id is not given (and the id itself is valid)."""
    if value is None and id_field in info.data and info.data[id_field] is None:
        raise ValueError(str(NO_MEMBER))
    return value


# Pages: every list is paginated, limit ≤ 100.


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


class ByIdIn(Schema):
    id: UUID = Field(description="The id.")


class MemberStatsIn(Schema):
    pass


class MineIn(Schema):
    pass


class CurrentMemberIn(Schema):
    pass


class SettingsGetIn(Schema):
    pass


class DeletedOut(Schema):
    id: UUID


# A staff member, by id or by name


class MemberRefIn(Schema):
    id: UUID | None = Field(None, description=D_MEMBER_ID)
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    @field_validator("member")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _member_named(value, info, "id")


class MemberOfIn(Schema):
    member_id: UUID | None = Field(None, description=D_MEMBER_ID)
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    @field_validator("member")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _member_named(value, info, "member_id")


# Members


class MemberListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH_MEMBERS)
    first_name: Search | None = Field(
        None, description="Keep the records whose first name contains this."
    )
    last_name: Search | None = Field(
        None, description="Keep the records whose last name contains this."
    )
    email: Search | None = Field(
        None, description="Keep the records whose email contains this."
    )
    phone: Search | None = Field(
        None, description="Keep the records whose phone contains this."
    )
    status: MemberStatus | None = Field(
        None, description="Keep the records in this status."
    )
    role_id: UUID | None = Field(
        None, description="Keep the records with this role (by id)."
    )
    role_name: Search | None = Field(
        None, description="Keep the records with this role (by its exact name)."
    )
    is_bookable: bool | None = Field(
        None, description="Keep only the bookable (true) or the not bookable (false)."
    )
    hire_date_from: dt.date | None = Field(
        None, description="Keep the records hired on or after this date."
    )
    hire_date_to: dt.date | None = Field(
        None, description="Keep the records hired on or before this date."
    )
    color: Color | None = Field(
        None, description="Keep the records with this colour (#RRGGBB)."
    )
    user_id: UUID | None = Field(
        None, description="Keep the record linked to this business user."
    )
    sort: MemberSort = Field(
        "name", description="Column to sort by; a leading '-' sorts descending."
    )


class MemberIn(Schema):
    first_name: Name = Field(description=D_FIRST_NAME)
    last_name: Name = Field(description=D_LAST_NAME)
    email: Email = Field("", description=D_EMAIL)
    phone: Phone = Field("", description=D_PHONE)
    employee_number: EmployeeNumber = Field("", description=D_EMPLOYEE_NUMBER)
    role_id: UUID | None = Field(None, description=D_ROLE_ID)
    role: Text100 | None = Field(None, description=D_ROLE)
    user_id: UUID | None = Field(None, description=D_USER_ID, json_schema_extra=A_PERSON)
    hire_date: dt.date | None = Field(None, description=D_HIRE_DATE)
    status: MemberStatus = Field(
        "active", description="Status the record is born with; active by default."
    )
    is_bookable: bool = Field(True, description=D_BOOKABLE)
    booking_buffer: BookingBuffer = Field(0, description=D_BUFFER)
    color: Color = Field("", description=D_COLOR)
    specialties: str = Field("", description=D_SPECIALTIES)
    bio: str = Field("", description=D_BIO)
    hourly_rate: Cents = Field(0, description=D_HOURLY_RATE)
    commission_rate: Percent = Field(Decimal("0"), description=D_COMMISSION)
    notes: str = Field("", description=D_HR_NOTES)


class MemberPatchIn(MemberRefIn):
    """Only the fields sent are changed. ``null`` clears ``role_id``, ``user_id`` and ``hire_date``
    and leaves any other field as it is."""

    first_name: Name | None = Field(None, description=D_FIRST_NAME)
    last_name: Name | None = Field(None, description=D_LAST_NAME)
    email: Email | None = Field(None, description=D_EMAIL)
    phone: Phone | None = Field(None, description=D_PHONE)
    employee_number: EmployeeNumber | None = Field(None, description=D_EMPLOYEE_NUMBER)
    role_id: UUID | None = Field(
        None, description=D_ROLE_ID + " Send null to remove the role."
    )
    role: Text100 | None = Field(None, description=D_ROLE)
    user_id: UUID | None = Field(
        None, description=D_USER_ID + " Send null to unlink it.", json_schema_extra=A_PERSON
    )
    hire_date: dt.date | None = Field(
        None, description=D_HIRE_DATE + " Send null to clear it."
    )
    status: MemberStatus | None = Field(
        None,
        description="New status: active, on_leave or inactive (inactive refuses live time off).",
    )
    is_bookable: bool | None = Field(None, description=D_BOOKABLE)
    booking_buffer: BookingBuffer | None = Field(None, description=D_BUFFER)
    color: Color | None = Field(None, description=D_COLOR)
    specialties: str | None = Field(None, description=D_SPECIALTIES)
    bio: str | None = Field(None, description=D_BIO)
    hourly_rate: Cents | None = Field(None, description=D_HOURLY_RATE)
    commission_rate: Percent | None = Field(None, description=D_COMMISSION)
    notes: str | None = Field(None, description=D_HR_NOTES)


class TerminateIn(MemberRefIn):
    """``termination_date`` empty = today, in the business's time zone."""

    termination_date: dt.date | None = Field(
        None, description="Last working day (YYYY-MM-DD); empty means today."
    )
    reason: Text500 = Field(
        "", description="Why the person leaves (optional, up to 500 characters)."
    )


class BulkMemberIn(Schema):
    """One row of a batch. Its own problems (a blank name, a bad email or date, a negative rate, a role
    that is not this business's) skip the row with a reason; the rest of the batch goes in."""

    first_name: Text100 = Field(description=D_FIRST_NAME)
    last_name: Text100 = Field(description=D_LAST_NAME)
    email: _text(254) = Field("", description=D_EMAIL)
    phone: Phone = Field("", description=D_PHONE)
    role_id: UUID | None = Field(None, description=D_ROLE_ID)
    role: Text100 | None = Field(None, description=D_ROLE)
    # Any text up to 100: a date that does not parse skips its row (invalid_hire_date), not the batch.
    hire_date: _text(100) | None = Field(None, description=D_HIRE_DATE)
    hourly_rate: int = Field(0, le=99_999_999, description=D_HOURLY_RATE, json_schema_extra={"money": True})
    is_bookable: bool = Field(True, description=D_BOOKABLE)
    bio: str = Field("", description=D_BIO)
    specialties: str = Field("", description=D_SPECIALTIES)


class BulkCreateIn(Schema):
    members: list[BulkMemberIn] = Field(
        min_length=1,
        max_length=MAX_BULK,
        title=gettext_noop("Staff members"),
        description="The people to add, 1 to 100 rows; each one is born active.",
    )


class BulkSkippedOut(Schema):
    index: int = Field(description="Position of the row in the batch, from 0.")
    reason: str = Field(
        description="name_required, invalid_email, invalid_hire_date, negative_hourly_rate or role_not_found."
    )


class BulkCreatedOut(Schema):
    created: list[UUID]
    skipped: list[BulkSkippedOut]


class CompensationListIn(MemberListIn):
    """The directory's filters, sort and pages (a screen reads the pay of the very rows it shows), and
    one member by id."""

    id: UUID | None = Field(None, description="Only this staff member.")


class CommissionSummaryIn(PageIn):
    search: Search | None = Field(None, description="Text to look for in the name.")


class CommissionReportIn(Schema):
    period: CommissionPeriod = Field(
        "today",
        description="today (the default), yesterday, this_week (from Monday) or this_month (from the 1st), "
        "in business days up to today. date_from and date_to replace it.",
    )
    date_from: dt.date | None = Field(
        None, description="A period of your own: its first business day (YYYY-MM-DD), with date_to."
    )
    date_to: dt.date | None = Field(
        None,
        validate_default=True,
        description="A period of your own: its last business day (YYYY-MM-DD), at most 731 days after date_from.",
    )

    @field_validator("date_to")
    @classmethod
    def _own_period(cls, value: dt.date | None, info: ValidationInfo) -> dt.date | None:
        start = info.data.get("date_from")
        if (start is None) != (value is None):
            raise ValueError(str(PERIOD_BOTH_DAYS))
        if start is not None and value is not None:
            if value < start:
                raise ValueError(str(END_BEFORE_START))
            if (value - start).days >= MAX_AVAILABILITY_DAYS:
                raise ValueError(str(RANGE_TOO_LONG))
        return value


class MemberOut(Schema):
    id: UUID
    first_name: str
    last_name: str
    full_name: str
    email: str
    phone: str
    employee_number: str
    role_id: UUID | None
    role_name: str | None
    user_id: UUID | None = Field(
        description="The business user the record hangs from, if any."
    )
    status: MemberStatus
    is_bookable: bool
    hire_date: dt.date | None
    color: str


class MemberDetailOut(MemberOut):
    booking_buffer: int = Field(description="Minutes between appointments.")
    specialties: str
    bio: str
    created_at: dt.datetime
    updated_at: dt.datetime


class MemberMineOut(MemberDetailOut):
    hourly_rate: int = Field(description="Hourly rate in cents.")
    commission_rate: Decimal = Field(description="Commission, in percent.")


class MineOut(Schema):
    member: MemberMineOut | None = Field(
        description="The caller's own record; null without one."
    )


class CurrentMemberRecordOut(Schema):
    id: UUID
    full_name: str


class CurrentMemberOut(Schema):
    member: CurrentMemberRecordOut | None = Field(
        description="The caller's own record, its id and name only; null without one."
    )


class CompensationOut(Schema):
    id: UUID
    user_id: UUID | None
    full_name: str
    role_id: UUID | None
    role_name: str | None
    status: MemberStatus
    hourly_rate: int = Field(description="Hourly rate in cents.")
    commission_rate: Decimal = Field(description="Commission, in percent.")
    notes: str = Field(description="Private HR notes.")


class CommissionOut(Schema):
    """Who can earn a commission, with their rate. A sale names its professional by the record's id; what
    each one earned in a period is ``staff.commission.report``."""

    id: UUID = Field(description="The staff record's id.")
    user_id: UUID | None = Field(
        description="The business user's id; null when the record has none."
    )
    full_name: str
    role_id: UUID | None
    role_name: str | None
    commission_rate: Decimal = Field(
        description="Commission, in percent: commission = gross x rate / 100."
    )


MemberPage = Page[MemberOut]
CompensationPage = Page[CompensationOut]
CommissionPage = Page[CommissionOut]


class CommissionReportRow(Schema):
    member_id: UUID = Field(description="The staff record's id.")
    full_name: str
    role_name: str | None
    status: RecordStatus = Field(
        description="active or on_leave (who can earn a commission); inactive or terminated when they sold in the period."
    )
    commission_rate: Decimal = Field(description="Commission, in percent.")
    sold: int = Field(description="What they sold in the period, refunds taken off, in cents.")
    commission: int = Field(description="sold x rate / 100, in cents, rounded half up once.")


class CommissionReportOut(Schema):
    date_from: dt.date = Field(description="The period's first business day.")
    date_to: dt.date = Field(description="The period's last business day.")
    sales_available: bool = Field(
        description="False when the business has no Sales: there is nothing to work a commission out from."
    )
    rows: list[CommissionReportRow] = Field(
        description="Everyone who can earn a commission (active or on leave), also without sales, and whoever "
        "sold in the period though inactive or terminated, by name."
    )
    total_sold: int = Field(description="What the rows sold, in cents.")
    total_commission: int = Field(description="The rows' commissions added up, in cents.")


class MemberStatsOut(Schema):
    total: int = Field(description="Records that are not terminated.")
    active: int
    on_leave: int
    inactive: int
    absent_today: int = Field(
        description="People with approved time off covering today."
    )
    pending_time_off: int = Field(
        description="Time-off requests waiting for an answer."
    )


class TerminatedOut(Schema):
    id: UUID
    termination_date: dt.date


# Accounts: the «Hub user» a record can hang from


class AccountListIn(PageIn):
    search: Search | None = Field(None, description="Text to look for in the account's name or email.")
    user_id: UUID | None = Field(
        None, description="Only this business user (to name the one a record hangs from)."
    )


class AccountOut(Schema):
    user_id: UUID = Field(description="The business user's id, for user_id of a record.")
    name: str = Field(description="Its name, or its email when it has none.")


AccountPage = Page[AccountOut]


# Roles


class RoleListIn(PageIn):
    search: Search | None = Field(
        None, description="Text to look for in the name or the description."
    )
    is_active: bool | None = Field(
        None, description="Keep only the active (true) or the retired (false) roles."
    )
    color: Color | None = Field(
        None, description="Keep the roles with this colour (#RRGGBB)."
    )
    member_count_min: int | None = Field(
        None, ge=0, description="Keep the roles with at least this many active people."
    )
    member_count_max: int | None = Field(
        None, ge=0, description="Keep the roles with at most this many active people."
    )
    sort: RoleSort = Field(
        "name", description="Column to sort by; a leading '-' sorts descending."
    )


class RoleIn(Schema):
    name: Name = Field(
        description="Name of the role, unique in the business (e.g. «Stylist»)."
    )
    description: Text500 = Field("", description="What the role does (optional).")
    color: Color = Field("", description="Colour as #RRGGBB; empty for none.")
    order: int = Field(0, ge=0, le=MAX_ORDER, description="Position among the roles (0 first).")


class RolePatchIn(Schema):
    """Only the fields sent are changed; ``null`` leaves a field as it is."""

    id: UUID = Field(description="The role's id.")
    name: Name | None = Field(None, description="New name.")
    description: Text500 | None = Field(None, description="New description.")
    color: Color | None = Field(None, description="New colour as #RRGGBB.")
    order: int | None = Field(None, ge=0, le=MAX_ORDER, description="New position among the roles.")
    is_active: bool | None = Field(
        None,
        description="false retires the role (no longer offered); true brings it back.",
    )


class RoleOut(Schema):
    id: UUID
    name: str
    description: str
    color: str
    order: int
    is_active: bool
    member_count: int = Field(description="Active people with this role.")



class RoleResolveIn(Schema):
    """The role a member would take, as staff.member.create takes it: by id or by name."""

    role_id: UUID | None = Field(None, description=D_ROLE_ID)
    role: Text100 | None = Field(None, description=D_ROLE)


class RoleResolveOut(Schema):
    id: UUID | None = Field(description="The role's id; none when no role was given.")
    name: str | None = Field(description="The role's name; none when no role was given.")


RolePage = Page[RoleOut]


# Schedules


class DayIn(Schema):
    """One weekday (Monday = 0): a stretch with an optional break inside it."""

    weekday: int = Field(
        ge=0, le=6, description="Day of the week: 0 Monday … 6 Sunday."
    )
    start_time: dt.time = Field(
        dt.time(9), description="Start of the working day (HH:MM)."
    )
    end_time: dt.time = Field(
        dt.time(18), description="End of the working day (HH:MM), after the start."
    )
    break_start: dt.time | None = Field(
        None, description="Start of the break (HH:MM), inside the working day."
    )
    break_end: dt.time | None = Field(
        None,
        validate_default=True,
        description="End of the break (HH:MM); with its start, or neither.",
    )
    is_working: bool = Field(
        True,
        description="false = the person does not work that day (its hours are ignored).",
    )

    @field_validator("end_time")
    @classmethod
    def _ends_after_it_starts(cls, value: dt.time, info: ValidationInfo) -> dt.time:
        start = info.data.get("start_time")
        if start is not None and value <= start:
            raise ValueError(str(TIME_ORDER))
        return value

    @field_validator("break_end")
    @classmethod
    def _break_inside(
        cls, value: dt.time | None, info: ValidationInfo
    ) -> dt.time | None:
        if (
            "break_start" not in info.data
        ):  # break_start itself is invalid: its own error says so
            return value
        start = info.data["break_start"]
        if (start is None) != (value is None):
            raise ValueError(str(BREAK_PAIR))
        day_start, day_end = info.data.get("start_time"), info.data.get("end_time")
        if value is not None and day_start is not None and day_end is not None:
            if not day_start <= start < value <= day_end:
                raise ValueError(str(BREAK_INSIDE))
        return value


def _a_week(value: list[DayIn]) -> list[DayIn]:
    if not any(day.is_working for day in value):
        raise ValueError(str(NO_DAYS))
    weekdays = [day.weekday for day in value]
    if len(set(weekdays)) != len(weekdays):
        raise ValueError(str(WEEKDAY_REPEATED))
    return value


Week = Annotated[list[DayIn], AfterValidator(_a_week)]
D_DAYS = "The week: one entry per weekday, at least one working day; a weekday not sent is a day off."
#: How the schedule form names the week (the assistant's card names the datum by it).
WEEK = gettext_noop("Week")


def _valid_range(value: dt.date | None, info: ValidationInfo) -> dt.date | None:
    start = info.data.get("effective_from")
    if value is not None and start is not None and value < start:
        raise ValueError(str(SCHEDULE_RANGE))
    return value


class ScheduleIn(Schema):
    name: Text100 = Field(
        "", description="Name of the schedule; empty = «Regular schedule»."
    )
    is_default: bool = Field(
        True, description="Whether it is the person's usual schedule (only one is)."
    )
    effective_from: dt.date | None = Field(
        None, description="First day it applies (YYYY-MM-DD); empty = always."
    )
    effective_until: dt.date | None = Field(
        None, description="Last day it applies (YYYY-MM-DD); empty = no end."
    )
    days: Week = Field(title=WEEK, description=D_DAYS)
    member_id: UUID | None = Field(None, description=D_MEMBER_ID)
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    _valid_range = field_validator("effective_until")(_valid_range)

    @field_validator("member")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _member_named(value, info, "member_id")


class ScheduleUpdateIn(Schema):
    """Replaces the week. The other fields keep their value when not sent; ``null`` clears a date."""

    id: UUID = Field(description="The schedule's id.")
    name: Text100 | None = Field(
        None, description="New name; empty = «Regular schedule»."
    )
    is_default: bool | None = Field(
        None, description="Whether it becomes (or stops being) the usual schedule."
    )
    effective_from: dt.date | None = Field(
        None, description="First day it applies; null = always."
    )
    effective_until: dt.date | None = Field(
        None, description="Last day it applies; null = no end."
    )
    days: Week = Field(title=WEEK, description=D_DAYS)

    _valid_range = field_validator("effective_until")(_valid_range)


class SetActiveIn(Schema):
    id: UUID = Field(description="The schedule's id.")
    is_active: bool = Field(
        description="false: the schedule never governs a day; true: it does again."
    )


class ScheduleListIn(PageIn):
    member_id: UUID | None = Field(None, description=D_MEMBER_ID)
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    @field_validator("member")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _member_named(value, info, "member_id")


class DayOut(Schema):
    weekday: int = Field(description="0 Monday … 6 Sunday.")
    start_time: dt.time
    end_time: dt.time
    break_start: dt.time | None
    break_end: dt.time | None


class ScheduleOut(Schema):
    id: UUID
    member_id: UUID
    name: str
    is_default: bool
    effective_from: dt.date | None
    effective_until: dt.date | None
    is_active: bool
    days: list[DayOut] = Field(
        description="The working days; a weekday missing is a day off."
    )


SchedulePage = Page[ScheduleOut]


# Availability


class AvailabilityIn(MemberOfIn):
    date_from: dt.date = Field(
        description="First day (YYYY-MM-DD), in the business's calendar."
    )
    date_to: dt.date = Field(
        description="Last day (YYYY-MM-DD); at most 731 days after the first."
    )

    @field_validator("date_to")
    @classmethod
    def _range(cls, value: dt.date, info: ValidationInfo) -> dt.date:
        start = info.data.get("date_from")
        if start is not None:
            if value < start:
                raise ValueError(str(END_BEFORE_START))
            if (value - start).days >= MAX_AVAILABILITY_DAYS:
                raise ValueError(str(RANGE_TOO_LONG))
        return value


class IntervalOut(Schema):
    start: dt.time
    end: dt.time


class AbsenceOut(Schema):
    """An approved absence covering the day, without its type or reason."""

    is_full_day: bool
    start_time: dt.time | None
    end_time: dt.time | None


class AvailabilityDayOut(Schema):
    date: dt.date
    schedule_id: UUID | None = Field(
        description="The schedule that governs the day; null = none (do not refuse on shifts)."
    )
    shifts: list[IntervalOut] = Field(
        description="The working stretches of the day, split by the break."
    )
    time_off: list[AbsenceOut] = Field(
        description="Approved absences covering the day."
    )
    available: list[IntervalOut] = Field(
        description="The shifts minus the approved absences."
    )


class AvailabilityOut(Schema):
    member_id: UUID
    days: list[AvailabilityDayOut]


# Time off


class TimeOffFieldsIn(Schema):
    """Whole days, or the same hours on each day of the range; a full day drops any hours sent."""

    leave_type: LeaveType = Field(
        "vacation",
        description="vacation, sick (sick leave), personal, training or other.",
    )
    start_date: dt.date = Field(description="First day off (YYYY-MM-DD).")
    end_date: dt.date = Field(
        description="Last day off (YYYY-MM-DD), not before the first."
    )
    is_full_day: bool = Field(
        True,
        description="true = whole days; false = only the hours below, on each day.",
    )
    start_time: dt.time | None = Field(
        None,
        validate_default=True,
        description="From what time (HH:MM), for a part-day absence.",
    )
    end_time: dt.time | None = Field(
        None,
        validate_default=True,
        description="Until what time (HH:MM), for a part-day absence.",
    )
    reason: Text500 = Field(
        "", description="Why (optional; private, only for managers and the person)."
    )
    notes: Text2000 = Field(
        "", description="Notes (optional; private, only for managers and the person)."
    )

    @field_validator("end_date")
    @classmethod
    def _ends_after_it_starts(cls, value: dt.date, info: ValidationInfo) -> dt.date:
        start = info.data.get("start_date")
        if start is not None and value < start:
            raise ValueError(str(END_BEFORE_START))
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def _hours_of_a_part_day(
        cls, value: dt.time | None, info: ValidationInfo
    ) -> dt.time | None:
        if info.data.get("is_full_day", True):
            return value
        if value is None:
            raise ValueError(str(TIMES_REQUIRED))
        start = info.data.get("start_time")
        if info.field_name == "end_time" and start is not None and value <= start:
            raise ValueError(str(TIME_ORDER))
        return value

    @model_validator(mode="after")
    def _full_day_has_no_hours(self):
        if self.is_full_day:
            self.start_time = self.end_time = None
        return self


class TimeOffIn(TimeOffFieldsIn):
    member_id: UUID | None = Field(None, description=D_MEMBER_ID)
    member: MemberName | None = Field(None, validate_default=True, description=D_MEMBER)

    @field_validator("member")
    @classmethod
    def _named(cls, value: str | None, info: ValidationInfo) -> str | None:
        return _member_named(value, info, "member_id")


class TimeOffRequestIn(TimeOffFieldsIn):
    """The caller's own time off: the member is the one linked to the caller's user."""


class TimeOffListIn(PageIn):
    search: Search | None = Field(
        None, description="Text to look for in the person's name."
    )
    member_id: UUID | None = Field(
        None, description="Only this staff member's time off."
    )
    status: TimeOffStatus | None = Field(
        None, description="pending, approved, rejected or cancelled."
    )
    leave_type: LeaveType | None = Field(
        None, description="vacation, sick, personal, training or other."
    )
    is_full_day: bool | None = Field(
        None, description="Only whole days (true) or only part days (false)."
    )
    approved_by_id: UUID | None = Field(
        None, description="Only the time off approved by this business user."
    )
    date_from: dt.date | None = Field(
        None, description="Only the time off that reaches this day or later."
    )
    date_to: dt.date | None = Field(
        None, description="Only the time off that starts on this day or earlier."
    )
    start_date_from: dt.date | None = Field(
        None, description="Only the time off starting on or after this day."
    )
    start_date_to: dt.date | None = Field(
        None, description="Only the time off starting on or before this day."
    )
    end_date_from: dt.date | None = Field(
        None, description="Only the time off ending on or after this day."
    )
    end_date_to: dt.date | None = Field(
        None, description="Only the time off ending on or before this day."
    )
    sort: TimeOffSort = Field(
        "-start_date", description="Column to sort by; a leading '-' sorts descending."
    )


class TodayIn(PageIn):
    pass


class MyTimeOffIn(PageIn):
    pass


class TimeOffOut(Schema):
    id: UUID
    member_id: UUID
    member_name: str
    leave_type: LeaveType
    leave_type_label: str = Field(description="The type in the caller's language (e.g. Vacation).")
    start_date: dt.date
    end_date: dt.date
    is_full_day: bool
    start_time: dt.time | None
    end_time: dt.time | None
    status: TimeOffStatus
    approved_by_id: UUID | None = Field(description="The business user who approved it.")
    approved_at: dt.datetime | None


class TimeOffDetailOut(TimeOffOut):
    reason: str
    notes: str
    approved_by_name: str | None
    created_at: dt.datetime


TimeOffPage = Page[TimeOffOut]
TimeOffDetailPage = Page[TimeOffDetailOut]


# Settings


class SettingsIn(Schema):
    """The default working day, which proposes the week of a new schedule; only what is sent changes.
    The old module's other eight settings changed nothing and are retired: sending one is refused by
    its name."""

    model_config = ConfigDict(extra="forbid")

    default_work_start: dt.time | None = Field(
        None, description="Working day starts (HH:MM)."
    )
    default_work_end: dt.time | None = Field(
        None, description="Working day ends (HH:MM), after the start."
    )
    default_break_duration: int | None = Field(
        None,
        ge=0,
        le=480,
        description="Break duration, 0 to 480 minutes, shorter than the working day.",
    )


class SettingsOut(Schema):
    default_work_start: str = Field(description="HH:MM.")
    default_work_end: str = Field(description="HH:MM.")
    default_break_duration: int
