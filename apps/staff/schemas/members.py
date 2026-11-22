"""Schemas of the staff members: the directory, a record and its pay, leaving, and adding several at once."""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import AfterValidator, StringConstraints

from apps.staff.schemas.fields import (
    A_ROLE,
    D_ROLE,
    D_ROLE_ID,
    ROLE,
    Color,
    MemberRefIn,
    Name,
    Page,
    PageIn,
    Search,
    Text100,
    Text500,
    _both_ways,
    _text,
)
from base.schemas.assistant import names
from base.sensitive import TEAM_CONTACT

INVALID_EMAIL = _("Enter a valid email address.")

#: The most rows staff.member.bulk_create takes at once (the old module's batch).
MAX_BULK = 100

MemberStatus = Literal["active", "inactive", "on_leave"]

# Never by email or phone: only whoever sees the team's contact details may know their order.
MEMBER_SORTS = (
    "name",
    "first_name",
    "last_name",
    "role_name",
    "status",
    "is_bookable",
    "hire_date",
    "color",
    "user_id",
    "id",
)

MemberSort = _both_ways(MEMBER_SORTS)


def _email(value: str) -> str:
    if value:
        try:
            validate_email(value)
        except DjangoValidationError:
            raise ValueError(str(INVALID_EMAIL)) from None
    return value


Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254),
    AfterValidator(_email),
]
Phone = _text(20)
EmployeeNumber = _text(50)
Cents = Annotated[int, Field(ge=0, le=99_999_999, json_schema_extra={"money": True})]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
BookingBuffer = Annotated[int, Field(ge=0, le=240)]

D_SEARCH_MEMBERS = (
    "Text to look for in the name, employee number or role, and in the email and phone for whoever sees the team's "
    "contact details."
)
D_FIRST_NAME = "First name."
D_LAST_NAME = "Last name(s)."
D_EMAIL = "Email address; empty for none."
D_PHONE = "Phone number, as written; empty for none."
D_TEAM_EMAIL = "Email address; empty for none, and null for whoever does not see the team's contact details."
D_TEAM_PHONE = (
    "Phone number, as written; empty for none, and null for whoever does not see the team's contact details."
)
D_EMPLOYEE_NUMBER = "The business's own employee number; empty for none."
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


class MemberStatsIn(Schema):
    pass


class MineIn(Schema):
    pass


class CurrentMemberIn(Schema):
    pass


class MemberListIn(PageIn):
    search: Search | None = Field(None, description=D_SEARCH_MEMBERS)
    first_name: Search | None = Field(
        None, description="Keep the records whose first name contains this."
    )
    last_name: Search | None = Field(
        None, description="Keep the records whose last name contains this."
    )
    email: Search | None = Field(
        None, description="Keep the records whose email contains this.", json_schema_extra=TEAM_CONTACT
    )
    phone: Search | None = Field(
        None, description="Keep the records whose phone contains this.", json_schema_extra=TEAM_CONTACT
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
    role_id: UUID | None = Field(None, title=ROLE, description=D_ROLE_ID, json_schema_extra=A_ROLE)
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
        None, title=ROLE, description=D_ROLE_ID + " Send null to remove the role.", json_schema_extra=A_ROLE
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
    role_id: UUID | None = Field(None, title=ROLE, description=D_ROLE_ID, json_schema_extra=A_ROLE)
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


class MemberOut(Schema):
    id: UUID
    first_name: str
    last_name: str
    full_name: str
    email: str | None = Field(description=D_TEAM_EMAIL, json_schema_extra=TEAM_CONTACT)
    phone: str | None = Field(description=D_TEAM_PHONE, json_schema_extra=TEAM_CONTACT)
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
    # One's own record: their own contact details, whoever they are.
    email: str = Field(description=D_EMAIL)
    phone: str = Field(description=D_PHONE)
    hourly_rate: int = Field(description="Hourly rate in cents.", json_schema_extra={"money": True})
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
    hourly_rate: int = Field(description="Hourly rate in cents.", json_schema_extra={"money": True})
    commission_rate: Decimal = Field(description="Commission, in percent.")
    notes: str = Field(description="Private HR notes.")


MemberPage = Page[MemberOut]
CompensationPage = Page[CompensationOut]


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
